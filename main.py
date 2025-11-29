import asyncio
import json
import logging
import sys
from os import getenv, path

import aiofiles
import aiohttp
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from bs4 import BeautifulSoup
from dotenv import load_dotenv

OUTAGES_SRC_URL = 'https://t.me/s/ArmeniaBlackouts'
OUTAGE_CHECK_INTERVAL = 60 * 10  # seconds
CONF_PATH = 'config.json'

dp = Dispatcher()

notification_recipients_chat_ids: list[int] = []
latest_parsed_msg: str = ''


async def load_config() -> None:
    global notification_recipients_chat_ids, latest_parsed_msg

    if not path.exists(CONF_PATH):
        return

    async with (aiofiles.open(CONF_PATH, mode='r') as f):
        conf_raw = await f.read()
        conf = json.loads(conf_raw)
        notification_recipients_chat_ids = conf['notification_recipients_chat_ids']
        latest_parsed_msg = conf['latest_parsed_msg']


async def update_config() -> None:
    global notification_recipients_chat_ids, latest_parsed_msg

    async with (aiofiles.open(CONF_PATH, mode='w') as f):
        conf = {
            'notification_recipients_chat_ids': notification_recipients_chat_ids,
            'latest_parsed_msg': latest_parsed_msg,
        }
        await f.write(json.dumps(conf))


async def get_latest_outages() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(OUTAGES_SRC_URL) as resp:
            if resp.status != 200:
                raise ValueError(f'error getting latest outages from {OUTAGES_SRC_URL}: {resp.status}')
            return await resp.text()


async def parse_outages(raw: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []

    soup = BeautifulSoup(raw, 'html.parser')
    for full_msg_tag in soup.find_all('div', attrs={'class': 'tgme_widget_message_wrap js-widget_message_wrap'}):
        result.append((
            full_msg_tag.find('div', attrs={'class': 'tgme_widget_message_text js-message_text'}).text,
            full_msg_tag.find('a', attrs={'class': 'tgme_widget_message_date'}).attrs['href'],
        ))
    return result


async def notify_if_outage_at_svachyan(outage: str, outage_link: str, bot: Bot) -> None:
    outage = outage.lower()
    if 'свачян' in outage or ('малатия' in outage and 'а1' in outage):
        logging.info(f'outage detected {outage_link}, notifying recipients')
        for recipient_chat_id in notification_recipients_chat_ids:
            logging.info(f'notifying recipient {recipient_chat_id}')
            await bot.send_message(recipient_chat_id, outage_link)


async def check_and_notify_about_outages(bot: Bot) -> None:
    global latest_parsed_msg

    logging.info('checking outages...')
    outages = await parse_outages(await get_latest_outages())
    if latest_parsed_msg != '':
        parse_start_idx = 0
        for i, outage_tuple in enumerate(outages):
            if outage_tuple[1] == latest_parsed_msg:
                parse_start_idx = i
                break
        outages = outages[parse_start_idx:]

    latest_parsed_msg = outages[-1][1]
    for outage, outage_link in outages:
        await notify_if_outage_at_svachyan(outage, outage_link, bot)

    await update_config()


async def outages_check_routine(bot: Bot) -> None:
    await check_and_notify_about_outages(bot)

    while True:
        await asyncio.sleep(OUTAGE_CHECK_INTERVAL)
        await check_and_notify_about_outages(bot)


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    # Most event objects have aliases for API methods that can be called in events' context
    # For example if you want to answer to incoming message you can use `message.answer(...)` alias
    # and the target chat will be passed to :ref:`aiogram.methods.send_message.SendMessage`
    # method automatically or call API method directly via
    # Bot instance: `bot.send_message(chat_id=message.chat.id, ...)`
    notification_recipients_chat_ids.append(message.chat.id)
    await update_config()
    await message.answer(f"Hello, {html.bold(message.from_user.full_name)}!\n"
                         f"From now on you'll receive info messages regarding water and power outages at Svachyan street")


async def main() -> None:
    load_dotenv()
    await load_config()

    # Initialize Bot instance with default bot properties which will be passed to all API calls
    bot = Bot(token=getenv("BOT_TOKEN"), default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    asyncio.create_task(outages_check_routine(bot))

    # And the run events dispatching
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
