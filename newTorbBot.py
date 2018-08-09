import asyncio
import discord
from discord.ext import commands
import sqlite3, time
import configparser

# Config import
config = configparser.ConfigParser()
config.read("bot.ini")
bot_info = config["Bot info"]
bot_token = bot_info.get("token")
database_info = config["Database info"]
database_name = database_info.get("name")

# Constants
MAX_JOIN_IN_MONTH = 6
MAX_PLAYERS_IN_team = 4
GROUP_CONFIRM_TIMEOUT = 60 * 60 * 12
GROUP_CONFIRM_MAX_ATTEMPTS = 4
YES_EMOJI = "\U00002705"
NO_EMOJI = "\U0000274c"

conn = sqlite3.connect("queue.db")
c = conn.cursor()

c.execute('''create table if not exists queue (
	event_id integer primary key,
	player_mention text unique,
	player_nick text,
	in_team integer,
	team_name text,
	join_date text,
	state integer,
	played integer,
	ac text,
	max_hp integer,
	level integer,
	class text
	);''') 

	# State = 0 : Not involved in the Arena
	# State = 1 : In queue
	# State = 2 : In confirmation
	# State = 3 : In arena
	# State = 4 : In holding pattern

c.execute('''create unique index if not exists idx_player on queue(player_mention)''')

c.execute('''create table if not exists records (
	player_mention text,
	join_date text)''')

conn.commit()

description = '''A simple bot to handle an Arena queue'''

bot = commands.Bot(command_prefix='&', description=description)

def update_nick(ctx):
	'''A function to update the nicknames of a player'''
	c.execute("update queue set player_nick = ? where player_mention = ?", (ctx.message.author.nick,ctx.message.author.nick))
	conn.commit()

def hat_check(message, person, emojis = None):
	'''A sweet function that returns a predicate for the confirmation checks'''
	def check(payload):
		return payload.message_id == message.id and payload.user_id == person.id and (True if emojis is None else payload.emoji.name in emojis)
	return check

async def bool_confirm(ctx, message_text, timeout=None):
	person = ctx.message.author
	message = await ctx.send(message_text)
	await message.add_reaction(YES_EMOJI)
	await message.add_reaction(NO_EMOJI)
	while True:
		try:
			payload = await bot.wait_for("raw_reaction_add",timeout = 60,check = hat_check(message, person, [YES_EMOJI, NO_EMOJI]))
		except asyncio.TimeoutError:
			ret = False
			break
		if payload.emoji.name == YES_EMOJI:
			ret = True
			break
		if payload.emoji.name == NO_EMOJI:
			ret = False
			break
	await message.delete()
	return ret

async def confirm_join(ctx, message_text):
	shorcuts = [
		"first", "second", "third","fourth and last"]
	person = ctx.message.author
	i = 0
	while i < CONFIRM_GROUP_MAX_ATTEMPTS:
		message = await ctx.send(message_text+f"\nThis is my {shortcuts[i]} attempt at contacting you.")
		await message.react(YES_EMOJI)

		try:
			payload = await wait_for("raw_reaction_add", timeout = CONFIRM_GROUP_TIMEOUT, check = hat_check(message, person))
		except asyncio.TimeoutError:
			i+=1
			continue

		if payload.emoji.name == YES_EMOJI:
			ret = True
			break

def get_common_name(ctx):
	'''Usually you need the nick, but if the user doesn't have one, it will return None, this fixes that'''
	return ctx.message.author.nick if ctx.message.author.nick is not None else ctx.message.author.name

def increment_month(date):
	'''Kinda hacky, but it adds one month to a datetime'''
	b = date.split(" ")[0].split("-")
	b[0] = str(int(b[0]) + int(1 if b[1] == "12" else 0))
	b[1] = f"{(int(b[1])%12+1):02}"
	return "-".join(b) + " " + date.split(" ")[1]

def decrement_month(date):
	'''Kinda hacky, but it removes a month from a datetime'''
	b = date.split(" ")[0].split("-")
	b[0] = str(int(b[0]) - int(1 if b[1] == "01" else 0))
	b[1] = f"{((int(b[1])+10)%12)+1:02}"
	return "-".join(b) + " " + date.split(" ")[1]

def gen_my_team(ctx):
	c.execute('''select team_name, player_nick from queue where active = 1 and team_name = (select team_name from queue where player_mention = ? and active = 1);''',(ctx.message.author.mention,))
	data = c.fetchall()
	if data == []:
		return(f"{get_common_name(ctx)}, you are not in a team")
	else:
		return(f'{get_common_name(ctx)}, you are in team `{data["team_name"][0]}` with:\n'+"\n".join([f"- {i[1]}" for i in data]))

async def join_queue(ctx):
	c.execute(f"select count(*) from queue where state > 0 and player_mention = ?",(ctx.message.author.mention,))
	if c.fetchone()[0] != 0:
		await ctx.send(f"{get_common_name(ctx)}, you are already in the queue.")
		return
	c.execute(f"select count(*),min(join_date) from records where player_mention = ? and join_date > ?", (ctx.message.author.mention, decrement_month(str(ctx.message.created_at))))
	result = c.fetchone()
	if result[0] > 6:
		await ctx.send(f"{get_common_name(ctx)}, you have joined the Arena too many times this month, try again on {increment_month(result[1])}")
	c.execute('''replace into queue (player_mention, player_nick, in_team, team_name, join_date,
			state)
			values (?,?,0,"",?,1)''',
		(ctx.message.author.mention, ctx.message.author.nick, str(ctx.message.created_at)))
	conn.commit()
	await ctx.send(f"{get_common_name(ctx)}, you are now entering the arena, the fiery crucible in which the only true heroes are forged")

def leave_queue(player):
	c.execute('update queue set state = 0, in_team = 0, team_name = "" where player_mention = ?',(player,))
	conn.commit()

def add_to_record(player_mention, join_date):
	c.execute(f"insert into records (player_mention, join_date) values {player_mention}, {join_date}")
	conn.commit()



@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.command()
async def stats(ctx, ac = None, max_hp = None, level = None, *, class_desc = None):
	'''Used to record your stats
	Usage: &stats AC max_HP level class and archetype
	Exemple: &stats 15 21 3 Monk Way of the Open Hand'''
	c.execute("select ac, max_hp, level, class from queue where player_mention = ?",(ctx.message.author.mention,))
	row = c.fetchone()
	ac = 0 if ac is None else ac
	c.execute("replace into queue (player_mention, ac, max_hp, level, class) values (?,?,?,?,?)",(ctx.message.author.mention, ac, max_hp, level, class_desc))
	conn.commit()
	await ctx.send(f"Very well {get_common_name(ctx)}, you now have the stats\n**AC: {ac}\nHP: {max_hp}\nLevel: {level}\nClass: {class_desc}**")
	await asyncio.sleep(1)

@bot.command()
async def join(ctx):
	'''Use `&join` to join the Arena Queue'''
	await join_queue(ctx)

@bot.command()
async def leave(ctx):
	'''Use `&leave` to leave the Arena Queue'''
	confirmed = await bool_confirm(ctx, f"{get_common_name(ctx)}, are you sure you want to leave the queue?")
	if confirmed:
		leave_queue(ctx.message.author.mention)
		await ctx.send(f"Sad to see you go {get_common_name(ctx)}, come back soon!")
	else:
		await ctx.send(f"Glad you've decided to stay with us {get_common_name(ctx)}")

@bot.group()
async def team(ctx):
	'''You have reached the team commands. You can use:
	`&team create [team name]` to create a team.
	`&team invite <@User>` to invite someone to your team.
	`&team join <team_name> to join a team`
	`&team leave` to leave the team you are in.
	`&team info [team name]` to list who is in a team, use `&team info` to see your own team
	`&team stats [team name]` to see the stats of a team's members, use `&team stats` to see the stats of the next team in the arena
	`&team list` to see all teams, and their current states'''

	if ctx.invoked_subcommand is None:
		if ctx.subcommand_passed is None:
			await ctx.send("You have called `team` without a subcommand, try calling `!help team` for a list of subcommands")
		else:
			await ctx.send(f"The command `&team {ctx.subcommand_passed}` wasn't recognized, did you mistype?")
		return

@team.command()
async def create(ctx,*, team_name=None):
	'''Use `&team create [team_name]` to create a team

	`team_name` must not not be used by an active team
	If no team_name is given, it will be given the name `your_name's team`'''
	await ctx.send(f"Created team `{team_name}`")

@team.command()
async def invite(ctx, user):
	'''Use `&team invite <@User>` to invite someone

	THey will see a confirmation dialogue. If they confirm, they will join your group if there's room left'''
	pass

@team.command()
async def join(ctx):
	'''Use `&team join <group_name>` to join the team `team_name`

	If the team is full, you will be denied.
	If the team doesn't exist, it will offer you to create it.'''
	pass

@team.command()
async def leave(ctx):
	'''Use `&team leave` to leave your current group

	This will will prompt a confirmation dialogue
	You will join the queue as a filler at the time you started'''
	pass

@team.command()
async def info(ctx, *, team_name=None):
	'''Use `&team info [group_name]` to see info on a group

	If you don't pass a group_name, it will give info on the group you are in
	If you are a filler, this will do nothing'''
	pass

@team.command()
async def stats(ctx, *, team_name=None):
	'''Use `&team stats [group_name]` to see stats of a group'''
	pass

@team.command()
async def list(ctx):
	'''Use `&team list` to see all groups and their current status'''
	states_array = ["INVALID", "In Queue", "In Confirmation", "In Arena", "In Holding Pattern"]
	c.execute("select player_nick, in_team, team_name, state from queue where state > 0 group by state, in_team, team_name")
	players = c.fetchall()
	prev_in_team, prev_team_name, prev_state = 1, None, None
	for player in players:
		player_nick, in_team, team_name, state = player
		if prev_state != state:
			await ctx.send(f"__**{states_array()}**__")
		if prev_in_team == 1 and in_team == 0:
			await ctx.state(f"  -*Fillers*")
		elif prev_team_name != team_name:
			await ctx.state(f"  -Team: *{team_name}*")
		await ctx.send(f"    -{player_nick}")
		prev_in_team, prev_team_name, prev_state = in_team, team_name, state

@bot.command()
@commands.has_role("Admin")
async def kick(ctx, player, *, reason = None):
	'''(Admin Only) Kicks a player from the queue'''
	confirmed = await bool_confirm(ctx, f"{get_common_name(ctx)}, are you sure you want to kick {player} out of the queue?")
	if confirmed:
		leave_queue(player)
		await ctx.send(f"{player}, you have been kicked out of the queue{'' if reason is None else ('For the following reason: '+reason)}")


@bot.command()
@commands.has_role("Admin")
async def ban(ctx, user, days, *, reasons):
	'''(Admin Only) Bans a player from the queue, use a negative number of days for a permanent ban'''
	confirmed = await bool_confirm(ctx, f"{get_common_name(ctx)}, are you sure you want to ban {player} for {}")
	if confirmed:
		leave_queue(player)
		await ctx.send(f"{player}, you have been banned for{f' {days} days' if days is not None else 'ever'}{'' if reason is None else ('For the following reason: '+reason)}")


@bot.command()
@commands.has_role("Arena-Master")
async def next(ctx, user, days):
	'''(Arena-Master Only) Calls the next group up'''


@bot.command()
async def func(ctx):
	msg = await ctx.send("You sure?")
	await confirm(msg, ctx.message.author)

bot.run(bot_token)
