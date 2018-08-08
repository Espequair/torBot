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
YES_EMOJI = "\U00002705"
NO_EMOJI = "\U000026d4"

# SQL Shortcuts
ACTIVE = "(in_queue = 1) or (in_confirm = 1) or (in_arena = 1)"

conn = sqlite3.connect("queue.db")
c = conn.cursor()

c.execute('''create table if not exists queue (
	event_id integer primary key,
	player_mention text,
	player_nick text,
	in_team integer,
	team_name text,
	join_date text,
	in_queue integer,
	in_confirm integer,
	in_arena integer,
	played integer
	);''')

c.execute('''create table if not exists stats (
	player_mention text unique,
	ac text,
	max_hp text,
	level text,
	class text)''')
c.execute('''create unique index if not exists idx_player on stats(player_mention)''')
conn.commit()

description = '''A simple bot to handle an Arena queue'''

bot = commands.Bot(command_prefix='&', description=description)

async def bool_confirm(message, person):
	await message.add_reaction(YES_EMOJI)
	await message.add_reaction(NO_EMOJI)
	while True:
		payload = await bot.wait_for("raw_reaction_add")
		if payload.message_id != message.id or payload.user_id != person.id or (payload.emoji.name != YES_EMOJI and payload.emoji.name != NO_EMOJI):
			continue
		if payload.emoji.name == YES_EMOJI:
			ret = True
			break
		if payload.emoji.name == NO_EMOJI:
			ret = False
			break
	await message.delete()
	return ret

def get_common_name(ctx):
	return ctx.message.author.nick if ctx.message.author.nick is not None else ctx.message.author.name

def increment_month(date):
	b = date.split(" ")[0].split("-")
	b[0] = str(int(b[0]) + int(1 if b[1] == "12" else 0))
	b[1] = f"{(int(b[1])%12+1):02}"
	return "-".join(b) + " " + date.split(" ")[1]

def decrement_month(date):
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
	c.execute(f"select count(*) from queue where {ACTIVE} and player_mention = ?",(ctx.message.author.mention,))
	if c.fetchone()[0] != 0:
		await ctx.send(f"{ctx.message.author.nick}, you are already in the queue.")
		return
	c.execute('''insert into queue (player_mention,	player_nick, in_team, team_name, join_date,
			in_queue, in_confirm, in_arena, played)
			values (?,?,0,"",?,1,1,1,0)''',
		(ctx.message.author.mention, ctx.message.author.nick, ctx.message.created_at))
	conn.commit()
	await ctx.send(f"{ctx.message.author.nick}, you are now entering the arena, the Fiery Crucible in which true heroes are forged")

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.command()
async def stats(ctx, ac, max_hp, level, *, class_desc):
	'''Used to record your stats
	Usage: &stats AC max_HP level class and archetype
	Exemple: &stats 15 21 3 Monk Way of the Open Hand'''
	c.execute("replace into stats (player_mention, ac, max_hp, level, class) values (?,?,?,?,?)",(ctx.message.author.mention, ac, max_hp, level, class_desc))
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
	message = await ctx.send(f"{ctx.message.author.nick}, are you sure you want to leave the queue?")
	leave = await bool_confirm(message, ctx.message.author)
	if leave:
		c.execute("update queue set in_queue = 0, in_confirm = 0, in_arena = 0 where player_mention = ?",(ctx.message.author.mention,))
		conn.commit()
		await ctx.send(f"Sad to see you go {ctx.message.author.nick}, come back soon!")
	else:
		await ctx.send(f"Glad you've decided to stay with us {ctx.message.author.nick}")

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
	pass

@bot.command()
@commands.has_role("Admin")
async def kick(ctx, player):
	'''(Admin Only) Kicks a player from the queue'''
	pass

@bot.command()
@commands.has_role("Admin")
async def ban(ctx, user, days):
	'''(Admin Only) Bans a player from the queue, use a negative number of days for a permanent ban'''
	pass

@bot.command()
@commands.has_role("Arena-Master")
async def next(ctx, user, days):
	'''(Arena-Master Only) Calls the next group up'''
	pass

@bot.command()
async def func(ctx):
	msg = await ctx.send("You sure?")
	await confirm(msg, ctx.message.author)

bot.run(bot_token)
