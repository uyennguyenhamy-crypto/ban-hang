import os
import json
import re
import traceback
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# =========================================================
# CONFIG
# =========================================================
TOKEN = os.getenv("TOKEN")

SHOP_CHANNEL_ID = 1545458090789576723
TICKET_CATEGORY_ID = 1545889891144171580
STAFF_ROLE_ID = 1545776328937185300

# Khuyên đặt GUILD_ID trên Railway để slash command sync ngay lập tức.
# Nếu chưa đặt, bot vẫn sync global.
GUILD_ID = os.getenv("GUILD_ID")
DATA_FILE = "products.json"

# =========================================================
# DATABASE
# =========================================================
def load_products() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print("[DB] products.json không phải object -> reset.")
            return {}
        return data
    except Exception as e:
        print(f"[DB] Không đọc được products.json: {e}")
        return {}


def save_products() -> None:
    tmp = DATA_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        print(f"[DB] Không lưu được products.json: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


products = load_products()

# =========================================================
# BOT
# =========================================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

class ShopBot(commands.Bot):
    async def setup_hook(self):
        # Sync sau khi bot đã login, không sync trước bot.start().
        try:
            if GUILD_ID and GUILD_ID.isdigit():
                guild = discord.Object(id=int(GUILD_ID))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"[SYNC] Guild {GUILD_ID}: {len(synced)} commands")
            else:
                synced = await self.tree.sync()
                print(f"[SYNC] Global: {len(synced)} commands")
        except Exception as e:
            print(f"[SYNC ERROR] {type(e).__name__}: {e}")
            traceback.print_exc()

        self.add_view(ShopView())
        self.add_view(TicketView())
        print("[SETUP] Persistent views loaded")


bot = ShopBot(command_prefix="!", intents=intents)


def money(value: int) -> str:
    return f"{int(value):,}".replace(",", ".") + " VNĐ"


def parse_price(value: str) -> int:
    text = str(value).strip().lower().replace(" ", "")
    try:
        if text.endswith("k"):
            return int(float(text[:-1]) * 1000)
        if text.endswith("m"):
            return int(float(text[:-1]) * 1_000_000)
        digits = re.sub(r"[^0-9]", "", text)
        return int(digits) if digits else 0
    except ValueError:
        return 0


def is_staff(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or any(
        role.id == STAFF_ROLE_ID for role in member.roles
    )


def get_category(guild: discord.Guild):
    channel = guild.get_channel(TICKET_CATEGORY_ID)
    return channel if isinstance(channel, discord.CategoryChannel) else None


def get_shop_channel(guild: discord.Guild):
    channel = guild.get_channel(SHOP_CHANNEL_ID)
    return channel if isinstance(channel, discord.TextChannel) else None


def find_open_ticket(guild: discord.Guild, user_id: int):
    category = get_category(guild)
    if category is None:
        return None
    for channel in category.text_channels:
        if channel.topic == f"shop-ticket:{user_id}":
            return channel
    return None

# =========================================================
# SHOP MESSAGE
# =========================================================
def shop_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🛒 SHOP ONLINE",
        description=(
            "Chọn sản phẩm ở menu bên dưới để mua.\n\n"
            "📦 Chọn sản phẩm → 🔢 Nhập số lượng → ✅ Xác nhận → 🎫 Ticket"
        ),
        color=discord.Color.blurple(),
    )

    if not products:
        embed.add_field(
            name="📦 Sản phẩm",
            value="Chưa có sản phẩm. Nhân viên dùng `/themsp` để thêm.",
            inline=False,
        )
    else:
        for code, item in list(products.items())[:25]:
            name = str(item.get("name", code))
            price = int(item.get("price", 0))
            stock = int(item.get("stock", 0))
            status = f"🟢 Còn {stock}" if stock > 0 else "🔴 Hết hàng"
            embed.add_field(
                name=f"📦 {name[:240]}",
                value=f"💰 {money(price)}\n{status}\n🆔 `{code}`",
                inline=True,
            )
    embed.set_footer(text="Shop Bot")
    return embed


class ProductSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for code, item in list(products.items())[:25]:
            stock = int(item.get("stock", 0))
            if stock <= 0:
                continue
            options.append(
                discord.SelectOption(
                    label=str(item.get("name", code))[:100],
                    description=f"{money(item.get('price', 0))} • Kho: {stock}"[:100],
                    value=str(code),
                    emoji="📦",
                )
            )

        if not options:
            options = [
                discord.SelectOption(
                    label="Chưa có sản phẩm còn hàng",
                    description="Nhân viên hãy thêm hàng",
                    value="__none__",
                    emoji="❌",
                )
            ]

        super().__init__(
            placeholder="🛒 Chọn sản phẩm...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="shop_select_v2",
        )

    async def callback(self, interaction: discord.Interaction):
        code = self.values[0]
        if code == "__none__":
            await interaction.response.send_message("❌ Hiện chưa có sản phẩm còn hàng.", ephemeral=True)
            return

        item = products.get(code)
        if not item or int(item.get("stock", 0)) <= 0:
            await interaction.response.send_message("❌ Sản phẩm vừa hết hàng.", ephemeral=True)
            return

        await interaction.response.send_modal(QuantityModal(code))


class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProductSelect())

# =========================================================
# ORDER MODAL
# =========================================================
class QuantityModal(discord.ui.Modal, title="🛒 Đặt hàng"):
    quantity = discord.ui.TextInput(
        label="Số lượng",
        placeholder="Ví dụ: 1",
        min_length=1,
        max_length=6,
        required=True,
    )

    def __init__(self, code: str):
        super().__init__()
        self.code = code

    async def on_submit(self, interaction: discord.Interaction):
        item = products.get(self.code)
        if not item:
            await interaction.response.send_message("❌ Sản phẩm không tồn tại.", ephemeral=True)
            return

        try:
            qty = int(str(self.quantity.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Số lượng phải là số nguyên.", ephemeral=True)
            return

        stock = int(item.get("stock", 0))
        if qty <= 0:
            await interaction.response.send_message("❌ Số lượng phải lớn hơn 0.", ephemeral=True)
            return
        if qty > stock:
            await interaction.response.send_message(f"❌ Kho chỉ còn **{stock}**.", ephemeral=True)
            return

        total = int(item.get("price", 0)) * qty
        embed = discord.Embed(title="📋 XÁC NHẬN ĐƠN HÀNG", color=discord.Color.gold())
        embed.add_field(name="📦 Sản phẩm", value=str(item.get("name", self.code)), inline=False)
        embed.add_field(name="🔢 Số lượng", value=str(qty), inline=True)
        embed.add_field(name="💰 Đơn giá", value=money(item.get("price", 0)), inline=True)
        embed.add_field(name="💵 Tổng tiền", value=f"**{money(total)}**", inline=False)

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(self.code, qty),
            ephemeral=True,
        )

# =========================================================
# CONFIRM ORDER
# =========================================================
class ConfirmView(discord.ui.View):
    def __init__(self, code: str, qty: int):
        super().__init__(timeout=300)
        self.code = code
        self.qty = qty

    @discord.ui.button(label="Xác nhận đơn", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ACK ngay để không timeout trong lúc tạo channel.
        await interaction.response.defer(ephemeral=True, thinking=True)

        if interaction.guild is None:
            await interaction.followup.send("❌ Lệnh chỉ dùng trong server.", ephemeral=True)
            return

        item = products.get(self.code)
        if not item:
            await interaction.followup.send("❌ Sản phẩm không còn tồn tại.", ephemeral=True)
            return

        category = get_category(interaction.guild)
        if category is None:
            await interaction.followup.send(
                f"❌ Không tìm thấy Category ticket. ID hiện tại: `{TICKET_CATEGORY_ID}`",
                ephemeral=True,
            )
            return

        old = find_open_ticket(interaction.guild, interaction.user.id)
        if old:
            await interaction.followup.send(f"❌ Bạn đã có ticket: {old.mention}", ephemeral=True)
            return

        stock = int(item.get("stock", 0))
        if self.qty > stock:
            await interaction.followup.send(f"❌ Kho chỉ còn **{stock}**.", ephemeral=True)
            return

        guild = interaction.guild
        me = guild.me or guild.get_member(bot.user.id if bot.user else 0)
        if me is None or not me.guild_permissions.manage_channels:
            await interaction.followup.send("❌ Bot thiếu quyền **Manage Channels**.", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
        }
        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )

        safe = re.sub(r"[^a-zA-Z0-9-]", "", interaction.user.name)[:20] or "user"
        try:
            ticket = await guild.create_text_channel(
                name=f"ticket-{safe}",
                category=category,
                overwrites=overwrites,
                topic=f"shop-ticket:{interaction.user.id}",
                reason="Shop order",
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ Bot bị Discord từ chối tạo ticket. Kiểm tra quyền Manage Channels.", ephemeral=True)
            return
        except discord.HTTPException as e:
            print(f"[TICKET CREATE] {type(e).__name__}: {e}")
            await interaction.followup.send("❌ Discord lỗi khi tạo ticket. Xem log Railway.", ephemeral=True)
            return

        # Chỉ trừ kho sau khi tạo ticket thành công.
        item["stock"] = stock - self.qty
        save_products()

        total = int(item.get("price", 0)) * self.qty
        embed = discord.Embed(
            title="🎫 ĐƠN HÀNG MỚI",
            description="Nhân viên kiểm tra đơn và hỗ trợ khách.",
            color=discord.Color.green(),
        )
        embed.add_field(name="👤 Khách", value=interaction.user.mention, inline=False)
        embed.add_field(name="📦 Sản phẩm", value=str(item.get("name", self.code)), inline=False)
        embed.add_field(name="🔢 Số lượng", value=str(self.qty), inline=True)
        embed.add_field(name="💰 Đơn giá", value=money(item.get("price", 0)), inline=True)
        embed.add_field(name="💵 Tổng", value=f"**{money(total)}**", inline=False)
        embed.add_field(name="📦 Kho còn", value=str(item["stock"]), inline=True)

        staff_mention = staff_role.mention if staff_role else "@Staff"
        try:
            await ticket.send(
                content=f"{interaction.user.mention} {staff_mention}",
                embed=embed,
                view=TicketView(),
            )
        except Exception as e:
            print(f"[TICKET MESSAGE] {type(e).__name__}: {e}")

        await interaction.followup.send(
            "✅ **Đặt hàng thành công!**\n"
            f"📦 {item.get('name', self.code)}\n"
            f"🔢 Số lượng: **{self.qty}**\n"
            f"💵 Tổng: **{money(total)}**\n"
            f"🎫 Ticket: {ticket.mention}",
            ephemeral=True,
        )
        await refresh_shop(guild)

    @discord.ui.button(label="Hủy", emoji="❌", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Đã hủy đơn.", embed=None, view=None)

# =========================================================
# TICKET CLOSE
# =========================================================
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Đóng ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close_v2",
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
            await interaction.response.send_message("❌ Chỉ Staff mới được đóng ticket.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ Không phải ticket text channel.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 Đang đóng ticket...")
        try:
            await interaction.channel.edit(
                name=f"closed-{interaction.channel.name}"[:100],
                reason="Ticket closed",
            )
            await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=False)
        except Exception as e:
            print(f"[TICKET CLOSE] {type(e).__name__}: {e}")

# =========================================================
# SHOP REFRESH
# =========================================================
async def refresh_shop(guild: discord.Guild) -> bool:
    channel = get_shop_channel(guild)
    if channel is None:
        print(f"[SHOP] Không tìm thấy TextChannel {SHOP_CHANNEL_ID}")
        return False

    try:
        # Chỉ xóa message shop của bot, không đụng tin nhắn khác.
        async for msg in channel.history(limit=100):
            if msg.author == bot.user and msg.embeds and msg.embeds[0].title == "🛒 SHOP ONLINE":
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass

        await channel.send(embed=shop_embed(), view=ShopView())
        print(f"[SHOP] Đã refresh #{channel.name}")
        return True
    except discord.Forbidden:
        print("[SHOP] Bot thiếu View Channel / Send Messages / Manage Messages")
    except discord.HTTPException as e:
        print(f"[SHOP] HTTP error: {e}")
    return False

# =========================================================
# STAFF COMMAND CHECK
# =========================================================
def require_staff(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and is_staff(interaction.user)

# =========================================================
# SLASH COMMANDS
# =========================================================
@bot.tree.command(name="themsp", description="Thêm sản phẩm vào shop")
@app_commands.describe(ma="Mã sản phẩm", ten="Tên sản phẩm", gia="Giá: 50k / 50000 / 1m", kho="Số lượng kho")
async def themsp(interaction: discord.Interaction, ma: str, ten: str, gia: str, kho: int):
    await interaction.response.defer(ephemeral=True)
    try:
        if not require_staff(interaction):
            await interaction.followup.send("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
            return
        code = ma.strip().lower()
        name = ten.strip()
        price = parse_price(gia)
        if not re.fullmatch(r"[a-z0-9_-]{1,30}", code):
            await interaction.followup.send("❌ Mã chỉ gồm a-z, 0-9, `_`, `-`.", ephemeral=True)
            return
        if not name or price <= 0 or kho < 0:
            await interaction.followup.send("❌ Tên, giá hoặc kho không hợp lệ.", ephemeral=True)
            return
        if code in products:
            await interaction.followup.send("❌ Mã sản phẩm đã tồn tại.", ephemeral=True)
            return

        products[code] = {"name": name, "price": price, "stock": kho}
        save_products()
        await interaction.followup.send(
            f"✅ Đã thêm **{name}**\n💰 {money(price)}\n📦 Kho: **{kho}**",
            ephemeral=True,
        )
        if interaction.guild:
            await refresh_shop(interaction.guild)
    except Exception as e:
        print(f"[THEMSP] {type(e).__name__}: {e}")
        traceback.print_exc()
        await interaction.followup.send("❌ Có lỗi khi thêm sản phẩm. Xem log Railway.", ephemeral=True)


@bot.tree.command(name="xoasp", description="Xóa sản phẩm")
@app_commands.describe(ma="Mã sản phẩm")
async def xoasp(interaction: discord.Interaction, ma: str):
    await interaction.response.defer(ephemeral=True)
    try:
        if not require_staff(interaction):
            await interaction.followup.send("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
            return
        code = ma.strip().lower()
        if code not in products:
            await interaction.followup.send("❌ Không tìm thấy sản phẩm.", ephemeral=True)
            return
        name = products[code].get("name", code)
        del products[code]
        save_products()
        await interaction.followup.send(f"🗑️ Đã xóa **{name}**.", ephemeral=True)
        if interaction.guild:
            await refresh_shop(interaction.guild)
    except Exception as e:
        print(f"[XOASP] {type(e).__name__}: {e}")
        traceback.print_exc()
        await interaction.followup.send("❌ Có lỗi. Xem log Railway.", ephemeral=True)


@bot.tree.command(name="sua_sp", description="Sửa sản phẩm")
@app_commands.describe(ma="Mã sản phẩm", gia="Giá mới (để trống nếu không sửa)", kho="Kho mới (để trống nếu không sửa)")
async def sua_sp(interaction: discord.Interaction, ma: str, gia: Optional[str] = None, kho: Optional[int] = None):
    await interaction.response.defer(ephemeral=True)
    try:
        if not require_staff(interaction):
            await interaction.followup.send("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
            return
        code = ma.strip().lower()
        if code not in products:
            await interaction.followup.send("❌ Không tìm thấy sản phẩm.", ephemeral=True)
            return
        if gia is None and kho is None:
            await interaction.followup.send("❌ Nhập `gia` hoặc `kho` để sửa.", ephemeral=True)
            return

        item = products[code]
        if gia is not None:
            price = parse_price(gia)
            if price <= 0:
                await interaction.followup.send("❌ Giá không hợp lệ.", ephemeral=True)
                return
            item["price"] = price
        if kho is not None:
            if kho < 0:
                await interaction.followup.send("❌ Kho không được âm.", ephemeral=True)
                return
            item["stock"] = kho
        save_products()
        await interaction.followup.send(
            f"✅ Đã sửa **{item['name']}**\n💰 {money(item['price'])}\n📦 Kho: **{item['stock']}**",
            ephemeral=True,
        )
        if interaction.guild:
            await refresh_shop(interaction.guild)
    except Exception as e:
        print(f"[SUASP] {type(e).__name__}: {e}")
        traceback.print_exc()
        await interaction.followup.send("❌ Có lỗi. Xem log Railway.", ephemeral=True)


@bot.tree.command(name="xemsp", description="Xem danh sách sản phẩm")
async def xemsp(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if not require_staff(interaction):
            await interaction.followup.send("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
            return
        embed = discord.Embed(title="📦 DANH SÁCH SẢN PHẨM", color=discord.Color.blurple())
        if not products:
            embed.description = "Shop chưa có sản phẩm."
        else:
            for code, item in list(products.items())[:25]:
                embed.add_field(
                    name=str(item.get("name", code)),
                    value=f"🆔 `{code}`\n💰 {money(item.get('price', 0))}\n📦 Kho: **{item.get('stock', 0)}**",
                    inline=False,
                )
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        print(f"[XEMSP] {type(e).__name__}: {e}")
        traceback.print_exc()
        await interaction.followup.send("❌ Có lỗi. Xem log Railway.", ephemeral=True)


@bot.tree.command(name="shop", description="Tạo/cập nhật bảng shop")
async def shop(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if not require_staff(interaction):
            await interaction.followup.send("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
            return
        if interaction.guild is None:
            await interaction.followup.send("❌ Lệnh chỉ dùng trong server.", ephemeral=True)
            return
        ok = await refresh_shop(interaction.guild)
        await interaction.followup.send("✅ Đã cập nhật bảng shop." if ok else "❌ Không cập nhật được shop. Kiểm tra quyền/kênh.", ephemeral=True)
    except Exception as e:
        print(f"[SHOP CMD] {type(e).__name__}: {e}")
        traceback.print_exc()
        await interaction.followup.send("❌ Có lỗi. Xem log Railway.", ephemeral=True)

# =========================================================
# ERROR HANDLING
# =========================================================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)
    print(f"[SLASH ERROR] {type(original).__name__}: {original}")
    traceback.print_exception(type(original), original, original.__traceback__)
    try:
        if interaction.response.is_done():
            await interaction.followup.send("❌ Bot gặp lỗi khi chạy lệnh. Xem log Railway.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot gặp lỗi khi chạy lệnh. Xem log Railway.", ephemeral=True)
    except Exception as e:
        print(f"[ERROR REPLY] {e}")

# =========================================================
# STARTUP / SYNC
# =========================================================
@bot.event
async def on_ready():
    print("========================================")
    print(f"BOT: {bot.user} | ID: {bot.user.id if bot.user else 'unknown'}")
    print(f"SHOP CHANNEL: {SHOP_CHANNEL_ID}")
    print(f"TICKET CATEGORY: {TICKET_CATEGORY_ID}")
    print(f"STAFF ROLE: {STAFF_ROLE_ID}")
    print("========================================")


@bot.event
async def on_error(event, *args, **kwargs):
    print(f"[EVENT ERROR] {event}")
    traceback.print_exc()


async def main():
    if not TOKEN:
        raise RuntimeError("TOKEN chưa được đặt trong Railway Variables")
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
