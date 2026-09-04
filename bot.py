import os
import json
import re
import discord
from discord.ext import commands
from discord import app_commands

# ============================================================
# CẤU HÌNH
# ============================================================

TOKEN = os.getenv("TOKEN")

SHOP_CHANNEL_ID = 1545458090789576723
TICKET_CATEGORY_ID = 1545458506755473458

STAFF_ROLE_IDS = {
    1537485808229949483,
    1537485814676848690,
    1537485810570498179,
}

DATA_FILE = "products.json"

# ============================================================
# BOT
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="?", intents=intents)


# ============================================================
# DATABASE
# ============================================================

def load_products():
    if not os.path.exists(DATA_FILE):
        return {}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError) as e:
        print(f"[DB] Không đọc được products.json: {e}")

    return {}


def save_products():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[DB] Không lưu được products.json: {e}")


products = load_products()


# ============================================================
# HÀM TIỆN ÍCH
# ============================================================

def money(value):
    return f"{int(value):,}".replace(",", ".") + " VNĐ"


def parse_price(text):
    text = str(text).strip().lower().replace(" ", "")

    try:
        if text.endswith("k"):
            return int(float(text[:-1]) * 1000)
        if text.endswith("m"):
            return int(float(text[:-1]) * 1_000_000)

        text = re.sub(r"[^0-9]", "", text)
        return int(text) if text else 0
    except ValueError:
        return 0


def is_staff(member: discord.Member):
    return (
        member.guild_permissions.administrator
        or any(role.id in STAFF_ROLE_IDS for role in member.roles)
    )


def get_staff_roles(guild: discord.Guild):
    return [
        role for role_id in STAFF_ROLE_IDS
        if (role := guild.get_role(role_id)) is not None
    ]


def find_user_ticket(category, user_id):
    if not isinstance(category, discord.CategoryChannel):
        return None

    for channel in category.text_channels:
        if channel.topic == f"ticket:{user_id}":
            return channel

    return None


# ============================================================
# SHOP EMBED
# ============================================================

def make_shop_embed():
    embed = discord.Embed(
        title="🛍️ SHOP ONLINE",
        description=(
            "Chọn sản phẩm bên dưới để đặt hàng.\n\n"
            "📦 Chọn sản phẩm → 🔢 Nhập số lượng → "
            "✅ Xác nhận → 🎫 Tạo ticket\n\n"
            "💡 Giá và số lượng trong kho được hiển thị trực tiếp."
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
            stock = int(item.get("stock", 0))
            status = f"🟢 Còn {stock}" if stock > 0 else "🔴 Hết hàng"

            embed.add_field(
                name=f"📦 {item.get('name', code)}",
                value=(
                    f"💰 {money(item.get('price', 0))}\n"
                    f"{status}\n"
                    f"🆔 `{code}`"
                ),
                inline=True,
            )

    embed.set_footer(text="Shop Bot")
    return embed


# ============================================================
# SHOP SELECT
# ============================================================

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
                    description=(
                        f"{money(item.get('price', 0))} • Kho: {stock}"
                    )[:100],
                    value=str(code),
                    emoji="📦",
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="Chưa có sản phẩm còn hàng",
                    description="Nhân viên hãy thêm hàng trước",
                    value="__empty__",
                    emoji="❌",
                )
            )

        super().__init__(
            placeholder="🛒 Chọn sản phẩm...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="shop_product_select",
        )

    async def callback(self, interaction: discord.Interaction):
        code = self.values[0]

        if code == "__empty__":
            await interaction.response.send_message(
                "❌ Hiện không có sản phẩm còn hàng.",
                ephemeral=True,
            )
            return

        item = products.get(code)
        if not item:
            await interaction.response.send_message(
                "❌ Sản phẩm không còn tồn tại.",
                ephemeral=True,
            )
            return

        if int(item.get("stock", 0)) <= 0:
            await interaction.response.send_message(
                "❌ Sản phẩm vừa hết hàng.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(QuantityModal(code))


class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProductSelect())


# ============================================================
# NHẬP SỐ LƯỢNG
# ============================================================

class QuantityModal(discord.ui.Modal, title="🛒 Nhập số lượng"):
    quantity = discord.ui.TextInput(
        label="Số lượng",
        placeholder="Ví dụ: 1",
        min_length=1,
        max_length=6,
    )

    def __init__(self, code):
        super().__init__()
        self.code = code

    async def on_submit(self, interaction: discord.Interaction):
        item = products.get(self.code)

        if not item:
            await interaction.response.send_message(
                "❌ Sản phẩm không tồn tại.",
                ephemeral=True,
            )
            return

        try:
            quantity = int(self.quantity.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Số lượng phải là số nguyên.",
                ephemeral=True,
            )
            return

        stock = int(item.get("stock", 0))

        if quantity <= 0:
            await interaction.response.send_message(
                "❌ Số lượng phải lớn hơn 0.",
                ephemeral=True,
            )
            return

        if quantity > stock:
            await interaction.response.send_message(
                f"❌ Kho chỉ còn **{stock}**.",
                ephemeral=True,
            )
            return

        total = int(item["price"]) * quantity

        embed = discord.Embed(
            title="📋 XÁC NHẬN ĐƠN HÀNG",
            color=discord.Color.gold(),
        )
        embed.add_field(name="📦 Sản phẩm", value=item["name"], inline=False)
        embed.add_field(name="🔢 Số lượng", value=str(quantity), inline=True)
        embed.add_field(name="💰 Đơn giá", value=money(item["price"]), inline=True)
        embed.add_field(name="💵 Tổng tiền", value=f"**{money(total)}**", inline=False)

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(self.code, quantity),
            ephemeral=True,
        )


# ============================================================
# XÁC NHẬN ĐƠN
# ============================================================

class ConfirmView(discord.ui.View):
    def __init__(self, code, quantity):
        super().__init__(timeout=300)
        self.code = code
        self.quantity = quantity

    @discord.ui.button(
        label="Xác nhận đơn",
        emoji="✅",
        style=discord.ButtonStyle.success,
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "❌ Không xác định được server.",
                ephemeral=True,
            )
            return

        item = products.get(self.code)
        if not item:
            await interaction.response.edit_message(
                content="❌ Sản phẩm không tồn tại.",
                embed=None,
                view=None,
            )
            return

        category = guild.get_channel(TICKET_CATEGORY_ID)

        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.edit_message(
                content=(
                    "❌ `TICKET_CATEGORY_ID` chưa đúng.\n"
                    f"ID đang dùng: `{TICKET_CATEGORY_ID}`\n\n"
                    "ID này phải là ID của **Category**, không phải kênh text."
                ),
                embed=None,
                view=None,
            )
            return

        old_ticket = find_user_ticket(category, interaction.user.id)
        if old_ticket:
            await interaction.response.edit_message(
                content=f"❌ Bạn đã có ticket: {old_ticket.mention}",
                embed=None,
                view=None,
            )
            return

        stock = int(item.get("stock", 0))
        if self.quantity > stock:
            await interaction.response.edit_message(
                content=f"❌ Kho chỉ còn **{stock}**.",
                embed=None,
                view=None,
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
        }

        staff_roles = get_staff_roles(guild)

        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )

        safe_name = re.sub(r"[^a-zA-Z0-9-]", "", interaction.user.name)[:20] or "user"
        channel_name = f"ticket-{safe_name}"

        try:
            ticket = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"ticket:{interaction.user.id}",
                reason="Shop order ticket",
            )
        except discord.Forbidden:
            await interaction.response.edit_message(
                content=(
                    "❌ Bot thiếu quyền tạo kênh.\n"
                    "Cấp cho bot quyền **Manage Channels**."
                ),
                embed=None,
                view=None,
            )
            return
        except discord.HTTPException as e:
            print(f"[TICKET] Discord API error: {e}")
            await interaction.response.edit_message(
                content="❌ Discord không thể tạo ticket. Xem Logs Railway.",
                embed=None,
                view=None,
            )
            return

        total = int(item["price"]) * self.quantity

        # Trừ kho sau khi ticket đã tạo thành công.
        item["stock"] = stock - self.quantity
        save_products()

        staff_mentions = " ".join(role.mention for role in staff_roles)
        if not staff_mentions:
            staff_mentions = "👮 Nhân viên"

        embed = discord.Embed(
            title="🎫 ĐƠN HÀNG MỚI",
            description="Nhân viên vui lòng kiểm tra và hỗ trợ khách.",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="👤 Khách hàng",
            value=interaction.user.mention,
            inline=False,
        )
        embed.add_field(
            name="📦 Sản phẩm",
            value=item["name"],
            inline=False,
        )
        embed.add_field(
            name="🔢 Số lượng",
            value=str(self.quantity),
            inline=True,
        )
        embed.add_field(
            name="💰 Đơn giá",
            value=money(item["price"]),
            inline=True,
        )
        embed.add_field(
            name="💵 TỔNG TIỀN",
            value=f"**{money(total)}**",
            inline=False,
        )
        embed.add_field(
            name="📦 Kho còn lại",
            value=str(item["stock"]),
            inline=True,
        )
        embed.set_footer(text="Shop Order System")

        await ticket.send(
            content=f"{interaction.user.mention} {staff_mentions}",
            embed=embed,
            view=TicketView(),
        )

        await interaction.response.edit_message(
            content=(
                "✅ **ĐẶT HÀNG THÀNH CÔNG!**\n\n"
                f"📦 {item['name']}\n"
                f"🔢 Số lượng: **{self.quantity}**\n"
                f"💵 Tổng: **{money(total)}**\n"
                f"🎫 Ticket: {ticket.mention}"
            ),
            embed=None,
            view=None,
        )

        await refresh_shop(guild)

    @discord.ui.button(
        label="Hủy",
        emoji="❌",
        style=discord.ButtonStyle.danger,
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Đã hủy đơn hàng.",
            embed=None,
            view=None,
        )


# ============================================================
# TICKET
# ============================================================

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Đóng ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close_button",
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            return

        if not is_staff(interaction.user):
            await interaction.response.send_message(
                "❌ Chỉ nhân viên mới được đóng ticket.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return

        await interaction.response.send_message("🔒 Ticket đã được đóng.")

        try:
            await channel.edit(
                name=f"closed-{channel.name}"[:100],
                reason="Ticket closed",
            )

            await channel.set_permissions(
                interaction.guild.default_role,
                view_channel=False,
            )

        except discord.HTTPException as e:
            print(f"[TICKET CLOSE] {e}")


# ============================================================
# REFRESH SHOP
# ============================================================

async def refresh_shop(guild: discord.Guild):
    channel = guild.get_channel(SHOP_CHANNEL_ID)

    if not isinstance(channel, discord.TextChannel):
        print(
            f"[SHOP] Không tìm thấy TextChannel "
            f"SHOP_CHANNEL_ID={SHOP_CHANNEL_ID}"
        )
        return

    try:
        async for message in channel.history(limit=100):
            if (
                message.author == bot.user
                and message.embeds
                and message.embeds[0].title == "🛍️ SHOP ONLINE"
            ):
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

        await channel.send(
            embed=make_shop_embed(),
            view=ShopView(),
        )
        print("[SHOP] Đã tạo bảng shop.")

    except discord.Forbidden:
        print("[SHOP] Bot thiếu View Channel / Send Messages / Manage Messages.")
    except discord.HTTPException as e:
        print(f"[SHOP] Discord API error: {e}")


# ============================================================
# SLASH COMMANDS
# ============================================================

@bot.tree.command(name="themsp", description="Thêm sản phẩm vào shop")
@app_commands.describe(
    ma="Mã sản phẩm, ví dụ acc01",
    ten="Tên sản phẩm",
    gia="Giá, ví dụ 50000 hoặc 50k",
    kho="Số lượng trong kho",
)
async def themsp(
    interaction: discord.Interaction,
    ma: str,
    ten: str,
    gia: str,
    kho: int,
):
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        await interaction.response.send_message(
            "❌ Bạn không có quyền dùng lệnh này.",
            ephemeral=True,
        )
        return

    code = ma.strip().lower()

    if not re.fullmatch(r"[a-z0-9_-]{1,30}", code):
        await interaction.response.send_message(
            "❌ Mã chỉ được dùng chữ thường, số, `_` hoặc `-`.",
            ephemeral=True,
        )
        return

    price = parse_price(gia)

    if price <= 0 or kho < 0:
        await interaction.response.send_message(
            "❌ Giá hoặc số lượng không hợp lệ.",
            ephemeral=True,
        )
        return

    if code in products:
        await interaction.response.send_message(
            "❌ Mã sản phẩm đã tồn tại.",
            ephemeral=True,
        )
        return

    products[code] = {
        "name": ten.strip(),
        "price": price,
        "stock": kho,
    }
    save_products()

    await interaction.response.send_message(
        (
            "✅ **Đã thêm sản phẩm**\n"
            f"📦 {ten}\n"
            f"💰 {money(price)}\n"
            f"📦 Kho: {kho}"
        ),
        ephemeral=True,
    )

    await refresh_shop(interaction.guild)


@bot.tree.command(name="xoasp", description="Xóa sản phẩm")
@app_commands.describe(ma="Mã sản phẩm")
async def xoasp(interaction: discord.Interaction, ma: str):
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        await interaction.response.send_message(
            "❌ Bạn không có quyền dùng lệnh này.",
            ephemeral=True,
        )
        return

    code = ma.strip().lower()

    if code not in products:
        await interaction.response.send_message(
            "❌ Không tìm thấy sản phẩm.",
            ephemeral=True,
        )
        return

    name = products[code]["name"]
    del products[code]
    save_products()

    await interaction.response.send_message(
        f"🗑️ Đã xóa **{name}**.",
        ephemeral=True,
    )

    await refresh_shop(interaction.guild)


@bot.tree.command(name="sua_sp", description="Sửa giá hoặc kho sản phẩm")
@app_commands.describe(
    ma="Mã sản phẩm",
    gia="Giá mới, ví dụ 50k",
    kho="Kho mới",
)
async def sua_sp(
    interaction: discord.Interaction,
    ma: str,
    gia: str | None = None,
    kho: int | None = None,
):
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        await interaction.response.send_message(
            "❌ Bạn không có quyền dùng lệnh này.",
            ephemeral=True,
        )
        return

    code = ma.strip().lower()

    if code not in products:
        await interaction.response.send_message(
            "❌ Không tìm thấy sản phẩm.",
            ephemeral=True,
        )
        return

    if gia is None and kho is None:
        await interaction.response.send_message(
            "❌ Hãy nhập `gia` hoặc `kho` cần sửa.",
            ephemeral=True,
        )
        return

    if gia is not None:
        price = parse_price(gia)
        if price <= 0:
            await interaction.response.send_message(
                "❌ Giá không hợp lệ.",
                ephemeral=True,
            )
            return
        products[code]["price"] = price

    if kho is not None:
        if kho < 0:
            await interaction.response.send_message(
                "❌ Kho không được âm.",
                ephemeral=True,
            )
            return
        products[code]["stock"] = kho

    save_products()

    await interaction.response.send_message(
        f"✅ Đã cập nhật **{products[code]['name']}**.",
        ephemeral=True,
    )

    await refresh_shop(interaction.guild)


@bot.tree.command(name="danhsachsp", description="Xem danh sách sản phẩm")
async def danhsachsp(interaction: discord.Interaction):
    if not products:
        await interaction.response.send_message(
            "📦 Shop chưa có sản phẩm.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="📦 DANH SÁCH SẢN PHẨM",
        color=discord.Color.blue(),
    )

    for code, item in list(products.items())[:25]:
        embed.add_field(
            name=item["name"],
            value=(
                f"🆔 `{code}`\n"
                f"💰 {money(item['price'])}\n"
                f"📦 Kho: **{item['stock']}**"
            ),
            inline=False,
        )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True,
    )


@bot.tree.command(name="capnhatshop", description="Tạo lại bảng shop")
async def capnhatshop(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not is_staff(interaction.user):
        await interaction.response.send_message(
            "❌ Bạn không có quyền dùng lệnh này.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    await refresh_shop(interaction.guild)
    await interaction.followup.send(
        "✅ Đã tạo lại bảng shop.",
        ephemeral=True,
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():
    print("=" * 55)
    print(f"🤖 Bot: {bot.user}")
    print(f"📦 Số sản phẩm: {len(products)}")
    print("=" * 55)

    # Đăng ký lại các View có custom_id để nút cũ vẫn hoạt động.
    if not getattr(bot, "_persistent_views_added", False):
        bot.add_view(ShopView())
        bot.add_view(TicketView())
        bot._persistent_views_added = True

    if not getattr(bot, "_commands_synced", False):
        try:
            guild_id = os.getenv("GUILD_ID")

            if guild_id:
                guild = discord.Object(id=int(guild_id))
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
                print(f"✅ Sync {len(synced)} slash command vào server.")
            else:
                synced = await bot.tree.sync()
                print(f"✅ Sync {len(synced)} slash command global.")

            bot._commands_synced = True

        except (ValueError, discord.HTTPException) as e:
            print(f"[SYNC] Lỗi: {e}")

    # Chỉ tạo bảng khi bot khởi động.
    if not getattr(bot, "_shop_initialized", False):
        bot._shop_initialized = True

        channel = bot.get_channel(SHOP_CHANNEL_ID)

        if isinstance(channel, discord.TextChannel):
            await refresh_shop(channel.guild)
        else:
            print(
                f"[SHOP] Không tìm thấy kênh "
                f"{SHOP_CHANNEL_ID}. Kiểm tra ID và quyền bot."
            )


# ============================================================
# START
# ============================================================

if not TOKEN:
    raise RuntimeError(
        "TOKEN chưa được đặt trong Railway Variables."
    )

bot.run(TOKEN)
