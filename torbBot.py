import asyncio
import discord
from discord.ext import commands
import sqlite3, time

# Constants
MAX_JOIN_IN_MONTH = 6
MAX_PLAYERS_IN_GROUP = 4

conn = sqlite3.connect("queue.db")
c = conn.cursor()

c.execute('''create table if not exists queue (event_id integer primary key, group_name text, player_mention text, player_nick text, join_date text, end_date text, active integer, played integer);''')
c.execute('''create table if not exists stats (player_mention text, ac text, max_hp text, level text, class text)''')
conn.commit()

description = '''A simple bot to handle an Arena queue'''

bot = commands.Bot(command_prefix='&', description=description)

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

def gen_my_group(ctx):
	c.execute('''select group_name from queue where (active = 1) and (player_mention = ?)''',(ctx.message.author.mention,))
	group = c.fetchone()
	if group is None:
		return(f"{get_common_name(ctx)}, you are not in a group")
	else:
		return(f"{get_common_name(ctx)}, you are in group `{group[0]}`")

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
	c.execute("delete from stats where player_mention = ?", (ctx.message.author.mention,))
	c.execute("insert into stats (player_mention, ac, max_hp, level, class) values (?,?,?,?,?)",(ctx.message.author.mention, ac, max_hp, level, class_desc))
	conn.commit()
	await ctx.send(f"Very well {get_common_name(ctx)}, you now have the stats\n**AC: {ac}\nHP: {max_hp}\nLevel: {level}\nClass: {class_desc}**")
	await asyncio.sleep(1)

@bot.command(alias = ["gi"])
async def group_info(ctx, team = None):
	'''Get more info about a group
	Usage: &group_info [group]
	this command will display the stats of the players inside the group passed
	selecting the next group to go if no group is given'''

	if team is None:
		c.execute("select group_name from queue where active = 1 order by join_date asc")
		team = c.fetchone()
		if team is None:
			await ctx.send("There doesn't seem to be a team in the queue currently")
			await asyncio.sleep(1)
			return None
		team = team[0]
	c.execute("select player_mention, player_nick from queue where active = 1 and group_name = ?",(team,))
	players = c.fetchall()
	if players == []:
		await ctx.send(f"I'm sorry {get_common_name(ctx)}, there doesn't seem to be a team by the name of `{team}` in the queue")
		await asyncio.sleep(1)
		return None
	await ctx.send(f"The members of group {team} are:")
	for player in players:
		c.execute("select * from stats where player_mention = ?",(player[0],))
		stats = c.fetchone()
		if stats is None:
			await ctx.send(f"{player[1]} hasn't told me their stats yet")
		else:
			await ctx.send(f"{player[1]} is a level {stats[3]} {stats[4]}\nThey have an AC of {stats[1]} and their max HP is {stats[1]}")
		await asyncio.sleep(1)

@bot.command()
async def join(ctx, *args):
	'''Used to join the arena queue

	Usage: &join [group_name]

	If no group name is given, it will default to "<your nickname>'s group"
	If another player wants to join your group, have him type &join [your_group_name]'''

	# We generate the name of the group, give it a default name if nothing was given
	group_name = " ".join(args) if len(args) > 0 else f"{get_common_name(ctx)}'s group"

	# We get the timestamp now to make sure it isn't thrown off by sqlite later
	timestamp = str(ctx.message.created_at)

	# If the user is already in the queue, and tries to rejoin the same group
	c.execute('''select group_name from queue where (player_mention = ?) and (active = 1) and (group_name = ?)''',(ctx.message.author.mention,group_name))
	rejoin_same = c.fetchone()
	if rejoin_same is not None:
		await ctx.send(f"{get_common_name(ctx)}, you were already in group `{group_name}`")
		await asyncio.sleep(1)
		return None

	# If the group already had 4 players, tell the player
	c.execute('''select count(*) from queue where (active = 1) and (group_name = ?)''',(group_name,))
	playercount = c.fetchone()
	if playercount is not None and playercount[0] >= MAX_PLAYERS_IN_GROUP:
		await ctx.send(f"I'm sorry {get_common_name(ctx)}, I'm afraid I can't let you do that, group `{group_name}` is already full")
		await asyncio.sleep(1)
		return None

	# If the user is already in the queue, and tries to join a different group
	c.execute('''select group_name from queue where (player_mention = ?) and (active = 1) and (group_name != ?)''',(ctx.message.author.mention,group_name))
	active_group = c.fetchone()
	if active_group is not None: 
		await ctx.send(f"{get_common_name(ctx)}, you were previously in group `{active_group[0]}`, you are now in group `{group_name}`")
		await asyncio.sleep(1)
		c.execute('''update queue set active = 0, end_date = ? where (active = 1) and(player_mention = ?)''',(ctx.message.created_at, ctx.message.author.mention,))
		c.execute('''insert into queue (group_name, player_mention, player_nick, join_date, end_date, active, played) 
				values
				(?,?,?,?,"0",1,0)''',
			(group_name, ctx.message.author.mention, get_common_name(ctx), ctx.message.created_at))
		conn.commit()
		return None

	# We make sure the number of joins is below the number needed
	c.execute('''select count(*) from queue where (player_mention = ?) and (played = 1) and (join_date > ?)''', (ctx.message.author.mention, decrement_month(timestamp)))
	join_in_last_month = c.fetchone()[0]
	if join_in_last_month >= MAX_JOIN_IN_MONTH:
		c.execute('''select join_date from queue where (player_mention = ?) and (played = 1) and (join_date > ?) Order by join_date limit 1''',(ctx.message.author.mention, decrement_month(timestamp)))
		join = increment_month(c.fetchone()[0])
		await ctx.send(f"I'm sorry {get_common_name(ctx)}, you have joined the queue too many times this month, try again at {join}")
		await asyncio.sleep(1)
		return None

	# Finally, we insert the value
	c.execute('''insert into queue (group_name, player_mention, player_nick, join_date, end_date, active, played) 
			values
			(?,?,?,?,"0",1,0)''',
		(group_name, ctx.message.author.mention, get_common_name(ctx), ctx.message.created_at))
	await ctx.send(f"{get_common_name(ctx)}, I have successfuly enrolled you in the group `{group_name}`\n To invite someone, have him type `&join {group_name}`")
	await asyncio.sleep(1)
	conn.commit()

@bot.command()
async def desist(ctx, *arg):
	'''Used to remove yourself from the arena queue

	Usage: &desist'''
	if len(arg) == 0:
		c.execute('''update queue set active = 0, end_date = ? where (active = 1) and (player_mention = ?)''',(ctx.message.created_at, ctx.message.author.mention))
		conn.commit()
		await ctx.send(f"{get_common_name(ctx)}, you have been removed from the Arena queue, I'll see you later")
		await asyncio.sleep(1)
		return None
	else:
		if "Admin" not in [i.name for i in ctx.message.author.roles]:
			await ctx.send(f"I'm sorry {get_common_name(ctx)}, I'm afraid I can't let you do that, you must be an Administrator to call this command")
			await asyncio.sleep(1)
			return None
		else:
			c.execute('''update queue set active = 0, end_date = ? where (active = 1) and (player_mention = ?)''',(ctx.message.created_at, arg[0]))
			conn.commit()
			await ctx.send(f"{get_common_name(ctx)}, I have successfully removed {arg[0]} from the Arena queue")
			await asyncio.sleep(1)
			return None

@bot.command()
async def invite(ctx, user):
	'''Invites an user over to your group
	Usage: &invite @User'''
	c.execute('''select group_name from queue where (active = 1) and player_mention = ?''',(ctx.message.author.mention,))
	group = c.fetchone()
	if group is None:
		await ctx.send(f"{get_common_name(ctx)}, you are not currently in a group, you can't invite someone!")
		await asyncio.sleep(1)
	else:
		await ctx.send(f"{user}, {get_common_name(ctx)} has invited you to their group: `{group[0]}`\nTo join their group, type `&join {group[0]}`")
		await asyncio.sleep(1)

@bot.command()
async def my_group(ctx):
	'''Prints the group you are in
	Usage: &group'''
	await ctx.send(gen_my_group(ctx))

@bot.command()
async def list(ctx):
	'''Lists the group currently in the queue
	Usage: &list'''
	await ctx.send(gen_my_group(ctx))
	c.execute('''select group_name, player_nick from queue where active = 1 order by join_date asc''')
	queue_list = c.fetchall()
	if queue_list is not None:
		ret_str = (f"Currently, there are {len(set([i[1] for i in queue_list]))} players in {len(set([i[0] for i in queue_list]))} groups in queue:" )
		for group in set([i[0] for i in queue_list]):
			ret_str += f"\n**{group}**:"
			c.execute('''select player_nick from queue where (active = 1) and (group_name = ?)''',(group,))
			for i in c.fetchall():
				ret_str += f"\n  -{i[0]}"
		await ctx.send(ret_str)
		await asyncio.sleep(1)
		return None

@bot.command(hidden = True)
async def next(ctx, *arg):
	if "Arena-Master" not in [i.name for i in ctx.message.author.roles]:
		await ctx.send(f"I'm sorry {get_common_name(ctx)}, I'm afraid I can't let you do that, you must be an Arena Master to call this command")
		await asyncio.sleep(1)
		return None
	c.execute('''select group_name from queue where active = 1 order by join_date asc''')
	group = c.fetchone()
	if group is None:
		await ctx.send("There doesn't seem to be anyone active in the queue")
	else:
		c.execute('''select player_mention from queue where (group_name = ?) and (active = 1)''', (group[0],))
		players = c.fetchall()
		for player in players:
			c.execute('''update queue set active = 0, played = 1, end_date = ? where (player_mention = ?)''', (ctx.message.created_at, player[0]))
			conn.commit()
			await ctx.send(f"I summon thee, {player[0]}. Come, and take your place in the arena")
			await asyncio.sleep(1)

bot.run('NDcyNDE3NzkzOTM0MDk4NDM1.DkntzA.N6aP-M1r1PnIzGwbpTz1X1a7yWk')
