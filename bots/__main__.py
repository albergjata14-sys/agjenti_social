"""python -m bots              -> lista e botëve
python -m bots sniper       -> roli dhe prompti i një boti"""
import sys

from bots import ALL_BOTS, get_bot

if len(sys.argv) > 1:
    bot = get_bot(" ".join(sys.argv[1:]))
    print(f"{bot.name}\nRoli: {bot.role}\nPrompti: {bot.prompt_file}\n")
    print(bot.prompt or "(ende pa prompt)")
else:
    for cls in ALL_BOTS:
        bot = cls()
        print(f"{'✅' if bot.ready else '⏳'} {bot.name:15} {bot.role}")
