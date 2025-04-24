import discord
import asyncio
import requests
import json
import os
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
import datetime

# Bot 設定
TOKEN = os.getenv("TOKEN")  # 從環境變數讀取
GUILD_ID = 1341784119016951883
CHANNEL_NAME = '補貨了-嗎'
URL = 'https://chiikawamarket.jp/collections/all'
SAVE_FILE = 'products.json'
THRESHOLD = 6500  # 商品數量安全閾值
CHECK_INTERVAL = 1200  # 每 20 分鐘檢查一次

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.members = True
client = discord.Client(intents=intents)

app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

async def fetch_product_info():
    headers = { "User-Agent": "Mozilla/5.0" }
    products = {}
    max_pages = 250

    for page_num in range(1, max_pages + 1):
        try:
            page_url = f"{URL}?page={page_num}"
            response = requests.get(page_url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"🚫 第 {page_num} 頁錯誤：{response.status_code}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('div.product--root')
            if not items:
                print(f"🛑 第 {page_num} 頁沒有商品了，停止抓取")
                break

            for product in items:
                a_tag = product.find('a', href=True)
                name_tag = product.select_one('h2.product_name')
                price_tag = product.select_one('div.product_price')
                image_tag = product.select_one('img[data-src]')

                if a_tag and name_tag:
                    link = a_tag['href']
                    name = name_tag.get_text(strip=True)
                    price = price_tag.get_text(strip=True) if price_tag else '未知'
                    image = image_tag['data-src'] if image_tag else None

                    if image and image.startswith('//'):
                        image = 'https:' + image
                    if '{width}' in image:
                        image = image.replace('{width}', '800')

                    products[link] = {
                        'name': name,
                        'price': price,
                        'image': image
                    }

            print(f"✅ 抓到第 {page_num} 頁 {len(items)} 件商品")

        except Exception as e:
            print(f"❌ 第 {page_num} 頁發生錯誤：{e}")
            break

    print(f"🎯 共抓到 {len(products)} 件商品")
    return products

def load_saved_products():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_products(products):
    with open(SAVE_FILE, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

async def run_once(channel, saved_products):
    try:
        new_products = await fetch_product_info()

        if len(new_products) < THRESHOLD:
            print(f"🚨 商品抓取異常（僅 {len(new_products)} 件），低於 {THRESHOLD}，跳過通知與比對。")
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
            with open(f"backup_products_{ts}.json", 'w', encoding='utf-8') as f:
                json.dump(new_products, f, ensure_ascii=False, indent=2)
            return saved_products  # 不更新主檔

        # 寫入正式 JSON
        save_products(new_products)

        removed_links = set(saved_products.keys()) - set(new_products.keys())
        added_links = set(new_products.keys()) - set(saved_products.keys())

        # 下架通知
        for link in removed_links:
            product = saved_products[link]
            embed = discord.Embed(
                title=f"❌ 商品下架了（可能補貨中）",
                description=f"**{product['name']}**\n價格：{product['price']}\n[查看商品](https://chiikawamarket.jp{link})",
                color=0xff6961
            )
            if product['image']:
                embed.set_thumbnail(url=product['image'])
            await channel.send(embed=embed)
            await asyncio.sleep(1.2)

        # 上架通知
        for link in added_links:
            product = new_products[link]
            embed = discord.Embed(
                title=f"🆕 新上架商品",
                description=f"**{product['name']}**\n價格：{product['price']}\n[查看商品](https://chiikawamarket.jp{link})",
                color=0x66ccff
            )
            if product['image']:
                embed.set_thumbnail(url=product['image'])
            await channel.send(embed=embed)
            await asyncio.sleep(1.2)

        await channel.send(
            f"📦 **Chiikawa 官網檢查完成**\n"
            f"目前商品總數：{len(new_products)} 件\n"
            f"新增商品：{len(added_links)} 件\n"
            f"下架商品：{len(removed_links)} 件"
        )

        return new_products

    except Exception as e:
        print(f"⚠️ 執行時發生錯誤：{e}")
        return saved_products

async def monitor_products():
    await client.wait_until_ready()
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        print(f"❌ 無法取得 GUILD（ID={GUILD_ID}）")
        return
    print(f"✅ 成功連接到伺服器：{guild.name}")
    channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
    if channel is None:
        print(f"❌ 找不到頻道 {CHANNEL_NAME}")
        return

    saved_products = load_saved_products()

    while not client.is_closed():
        saved_products = await run_once(channel, saved_products)
        print(f"⏳ 等待 {CHECK_INTERVAL // 60} 分鐘後再次檢查...")
        await asyncio.sleep(CHECK_INTERVAL)

@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')

@client.event
async def setup_hook():
    client.loop.create_task(monitor_products())

keep_alive()
client.run(TOKEN)
