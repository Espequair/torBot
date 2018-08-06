import asyncio
import discord
from discord.ext import commands
import sqlite3, time

# Constants
MAX_JOIN_IN_MONTH = 6
MAX_PLAYER_IN_GROUP = 4


conn = sqlite3.connect("queue.db")
c = conn.cursor()
description = '''An example bot to showcase the discord.ext.commands extension
module.
There are a number of utility commands being showcased here.'''
bot = commands.Bot(command_prefix='&', description=description)

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

def find_my_group(player_mention):
	c.execute('''select group_name from queue where (active = 1) and (player_mention = ?)''',(player_mention,))
	group = c.fetchone()
	return None if group is None else group[0]

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.command()
async def join(ctx, *args):
	group_name = " ".join(args) if len(args) > 0 else f"{ctx.message.author.nick}'s group"
	timestamp = str(ctx.message.created_at)
	c.execute('''Select * from queue''')
	rows = c.fetchall()
	for row in rows:
		print((row))

	# If the user is already in the queue, and tries to rejoin the same group
	c.execute('''select group_name from queue where (player_mention = ?) and (active = 1) and (group_name = ?)''',(ctx.message.author.mention,group_name))
	rejoin_same = c.fetchone()
	if rejoin_same is not None:
		await ctx.send(f"{ctx.message.author.nick}, you were already in group `{group_name}`")
		await asyncio.sleep(1)
		return None

	# If the group already had 4 players, tell the player
	c.execute('''select count(*) from queue where (active = 1) and (group_name = ?)''',(group_name,))
	playercount = c.fetchone()
	if playercount is not None and playercount[0] >= MAX_PLAYERS_IN_GROUP:
		await ctx.send(f"I'm sorry {ctx.message.author.nick}, I'm afraid I can't let you do that, group `{group_name}` is already full")
		await asyncio.sleep(1)
		return None

	# If the user is already in the queue, and tries to join a different group
	c.execute('''select group_name from queue where (player_mention = ?) and (active = 1) and (group_name != ?)''',(ctx.message.author.mention,group_name))
	active_group = c.fetchone()
	if active_group is not None: 
		await ctx.send(f"{ctx.message.author.nick}, you were previously in group `{active_group[0]}`, you are now in group `{group_name}`")
		await asyncio.sleep(1)
		c.execute('''update queue set active = 0 where player_mention = ?''',(ctx.message.author.mention,))

	# We make sure the number of joins is below 6
	c.execute('''select count(*) from queue where (player_mention = ?) and (played = 1) and (join_date > ?)''', (ctx.message.author.mention, decrement_month(timestamp)))
	join_in_last_month = c.fetchone()[0]
	print(join_in_last_month)
	if join_in_last_month >= MAX_JOIN_IN_MONTH:
		c.execute('''select join_date from queue where (player_mention = ?) and (played = 1) and (join_date > ?) Order by join_date limit 1''',(ctx.message.author.mention, decrement_month(timestamp)))
		join = increment_month(c.fetchone()[0])
		print(join)
		await ctx.send(f"I'm sorry {ctx.message.author.nick}, you have joined the queue too many times this month, try again at {join}")
		await asyncio.sleep(1)
		return None

	# Finally, we inser the value
	c.execute('''insert into queue (group_name, player_name, player_mention, join_date, end_date, active, played) 
			values
			(?,?,?,?,"0",1,0)''',
		(group_name, ctx.message.author.nick, ctx.message.author.mention, ctx.message.created_at))
	conn.commit()


@bot.command()
async def update(ctx, *arg):
	c.execute('''update queue set active = 0, played = 1, end_date = ?''',(ctx.message.created_at,))

@bot.command()
async def list(ctx, *arg):
	c.execute('''select group_name from queue where active = 1 order by join_date asc''')
	queue_list = c.fetchall()
	if queue_list is not None:
		await ctx.send(f"Currently, there are {len(queue_list)} groups in queue:\n" + "\n".join([i[0] for i in queue_list]))
		await asyncio.sleep(1)
		return None

@bot.command()
async def next(ctx, *arg):
	c.execute('''select group_name from queue where active = 1 order by join_date asc''')
	group = c.fetchone()
	if group is None:
		await ctx.send("There doesn't seem to be anyone active in the queue")
	else:
		c.execute('''select player_mention from queue where (group_name = ?) and (active = 1)''', (group[0],))
		players = c.fetchall()
		print(players)


@bot.command()
async def add(ctx, left: int, right: int):
    """Adds two numbers together."""
    await ctx.send(left + right)

bot.run('NDcyNDE3NzkzOTM0MDk4NDM1.DkhycQ.AR_VvrOwsRDm9VzB5qKR3oFqivM')
