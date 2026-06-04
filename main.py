import gc
import json
import logging
import sys
from os import path, getenv

import aiofiles
import aiohttp
from dotenv import load_dotenv
from lxml import html as lxml_html
from telegram import Update, Bot
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

OUTAGES_SRC_URL = 'https://t.me/s/ArmeniaBlackouts'
OUTAGE_CHECK_INTERVAL = 60 * 10  # seconds
CONF_PATH = 'config.json'

notification_recipients_chat_ids: list[int] = []
latest_parsed_msg: str = ''


def load_config() -> None:
    global notification_recipients_chat_ids, latest_parsed_msg

    if not path.exists(CONF_PATH):
        return

    with open(CONF_PATH, mode='r') as f:
        conf_raw = f.read()
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

    tree = lxml_html.fromstring(raw)

    message_blocks = tree.xpath(
        "//div[contains(@class, 'tgme_widget_message_wrap') and contains(@class, 'js-widget_message_wrap')]"
    )

    for full_msg_tag in message_blocks:
        text_nodes = full_msg_tag.xpath(
            ".//div[contains(@class, 'tgme_widget_message_text') and contains(@class, 'js-message_text')]"
        )

        if not text_nodes:
            continue

        text_node = text_nodes[0]

        for br in text_node.xpath(".//br"):
            br.tail = "\n" + br.tail if br.tail else "\n"

        text = text_node.text_content()

        date_nodes = full_msg_tag.xpath(
            ".//a[contains(@class, 'tgme_widget_message_date')]"
        )

        if not date_nodes:
            continue

        href = date_nodes[0].get("href")

        result.append((text, href))

    return result


def extract_outage_line(outage: str) -> str | None:
    for line in outage.splitlines():
        line_lower = line.lower()
        if 'свачян' in line_lower or ('малатия' in line_lower and 'а1' in line_lower):
            return line
    return None


async def notify_if_outage_at_svachyan(outage: str, outage_link: str, bot: Bot) -> None:
    outage_line = extract_outage_line(outage)
    if outage_line:
        logging.info(f'outage detected {outage_link}, notifying recipients')
        for recipient_chat_id in notification_recipients_chat_ids:
            logging.info(f'notifying recipient {recipient_chat_id}')
            await bot.send_message(recipient_chat_id, f'<blockquote>{outage_line}</blockquote>\n'
                                                      f'{outage_link}',
                                   parse_mode=ParseMode.HTML)


async def check_and_notify_about_outages(context: ContextTypes.DEFAULT_TYPE) -> None:
    global latest_parsed_msg

    logging.info('checking outages...')
    outages = await parse_outages(await get_latest_outages())
    if latest_parsed_msg != '':
        parse_start_idx = 0
        for i, outage_tuple in enumerate(outages):
            if outage_tuple[1] == latest_parsed_msg:
                parse_start_idx = i + 1
                break
        outages = outages[parse_start_idx:]
        if len(outages) == 0:
            return

    latest_parsed_msg = outages[-1][1]
    for outage, outage_link in outages:
        await notify_if_outage_at_svachyan(outage, outage_link, context.bot)

    await update_config()
    gc.collect()


async def command_start_handler(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    notification_recipients_chat_ids.append(update.message.chat_id)
    await update_config()
    await update.message.reply_html(
        f"Hello, <b>{update.message.from_user.full_name}</b>!\n"
        f"From now on you'll receive info messages regarding water and power outages at Svachyan street")


def main() -> None:
    load_dotenv()
    load_config()

    application = Application.builder().token(getenv("BOT_TOKEN")).build()
    application.add_handler(CommandHandler("start", command_start_handler))
    application.job_queue.run_repeating(
        check_and_notify_about_outages, interval=OUTAGE_CHECK_INTERVAL, first=1)
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)


if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.INFO, stream=sys.stdout)
    main()
