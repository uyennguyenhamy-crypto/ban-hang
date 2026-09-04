import os
import json
import re
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands


# =========================================================
# CẤU HÌNH
# =========================================================

TOKEN = os.getenv("TOKEN")

SHOP_CHANNEL_ID = 1545458090789576723
TICKET_CATEGORY_ID = 1545458506755473458

STAFF_ROLE_IDS = [
    1537485808229949483,
    1537485814676848690,
    1537485810570498179,
]

PRODUCT_FILE = "products.json"
TICKET_FILE = "tickets.json"


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="?",
    intents=intents
)


# =========================================================
# DATABASE
# =========================================================

def load_json(filename):
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception as e:
        print(f"❌ Lỗi đọc {filename}: {e}")

    return {}


def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )
    except Exception as e:
        print(f"❌ Lỗi lưu {filename}: {e}")


products = load_json(PRODUCT_FILE)
tickets = load_json(TICKET_FILE)


# =========================================================
# TIỆN ÍCH
# =========================================================

def money(value):
    return f"{int(value):,}".replace(",", ".") + " VNĐ"


def parse_price(value):
    text = str(value).lower().strip()
    text = text.replace(" ", "")

    multiplier = 1

    if text.endswith("k"):
        multiplier = 1000
        text = text[:-1]

    text = text.replace(".", "")
    text = text.replace(",", "")

    numbers = re.sub(r"[^0-9]", "", text)

    if not numbers:
        return 0

    return int(numbers) * multiplier


def is_staff(member):
    if member.guild_permissions.administrator:
        return True

    return any(
        role.id in STAFF_ROLE_IDS
        for role in member.roles
    )


def get_staff_roles(guild):
    roles = []

    for role_id in STAFF_ROLE_IDS:
        role = guild.get_role(role_id)

        if role:
            roles.append(role)

    return roles


def find_open_ticket(guild, user_id):
    for channel_id, data in tickets.items():

        if data.get("user_id") != user_id:
            continue

        if data.get("status") != "open":
            continue

        channel = guild.get_channel(int(channel_id))

        if channel:
            return channel

    return None


# =========================================================
# SHOP EMBED
# =========================================================

def create_shop_embed():

    embed = discord.Embed(
        title="🛒 SHOP ONLINE",
        description=(
            "Chào mừng bạn đến với shop!\n\n"
            "📦 **Bước 1:** Chọn sản phẩm\n"
            "🔢 **Bước 2:** Nhập số lượng\n"
            "📋 **Bước 3:** Kiểm tra đơn hàng\n"
            "✅ **Bước 4:** Xác nhận\n"
            "🎫 **Bước 5:** Ticket được tạo tự động\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 Giá và số lượng được cập nhật tự động."
        ),
        color=discord.Color.gold()
    )

    if not products:
        embed.add_field(
            name="📦 Sản phẩm",
            value="🔴 Shop hiện chưa có sản phẩm.",
            inline=False
        )
        return embed

    count = 0

    for product_id, product in products.items():

        stock = int(product.get("stock", 0))

        if stock <= 0:
            continue

        price = int(product.get("price", 0))

        name = product.get("name", product_id)

        embed.add_field(
            name=f"📦 {name}",
            value=(
                f"💰 Giá: **{money(price)}**\n"
                f"📦 Kho: **{stock}**"
            ),
            inline=True
        )

        count += 1

        if count >= 25:
            break

    if count == 0:
        embed.add_field(
            name="📦 Sản phẩm",
            value="🔴 Tất cả sản phẩm hiện đã hết hàng.",
            inline=False
        )

    embed.set_footer(
        text="Shop System • Chọn sản phẩm bên dưới để mua"
    )

    return embed


# =========================================================
# PRODUCT SELECT
# =========================================================

class ProductSelect(discord.ui.Select):

    def __init__(self):

        options = []

        available = []

        for product_id, product in products.items():

            stock = int(product.get("stock", 0))

            if stock <= 0:
                continue

            available.append(
                (product_id, product)
            )

        available = available[:25]

        for product_id, product in available:

            name = str(
                product.get(
                    "name",
                    product_id
                )
            )[:100]

            price = int(
                product.get(
                    "price",
                    0
                )
            )

            stock = int(
                product.get(
                    "stock",
                    0
                )
            )

            options.append(
                discord.SelectOption(
                    label=name,
                    description=(
                        f"{money(price)} • Kho {stock}"
                    )[:100],
                    value=product_id,
                    emoji="📦"
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="Shop chưa có hàng",
                    description="Hiện chưa có sản phẩm",
                    value="none",
                    emoji="❌"
                )
            )

        super().__init__(
            placeholder="🛒 Chọn sản phẩm...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="shop_product_select"
        )

    async def callback(self, interaction):

        product_id = self.values[0]

        if product_id == "none":
            await interaction.response.send_message(
                "❌ Hiện chưa có sản phẩm.",
                ephemeral=True
            )
            return

        if product_id not in products:
            await interaction.response.send_message(
                "❌ Sản phẩm không tồn tại.",
                ephemeral=True
            )
            return

        product = products[product_id]

        stock = int(
            product.get("stock", 0)
        )

        if stock <= 0:
            await interaction.response.send_message(
                "❌ Sản phẩm đã hết hàng.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            QuantityModal(product_id)
        )


# =========================================================
# SHOP VIEW
# =========================================================

class ShopView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProductSelect())


# =========================================================
# NHẬP SỐ LƯỢNG
# =========================================================

class QuantityModal(
    discord.ui.Modal,
    title="🛒 Đặt hàng"
):

    quantity = discord.ui.TextInput(
        label="Số lượng",
        placeholder="Ví dụ: 1",
        min_length=1,
        max_length=5,
        required=True
    )

    def __init__(self, product_id):

        super().__init__()

        self.product_id = product_id

    async def on_submit(self, interaction):

        product = products.get(
            self.product_id
        )

        if not product:
            await interaction.response.send_message(
                "❌ Sản phẩm không tồn tại.",
                ephemeral=True
            )
            return

        try:
            quantity = int(
                self.quantity.value
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Số lượng phải là số.",
                ephemeral=True
            )
            return

        if quantity <= 0:
            await interaction.response.send_message(
                "❌ Số lượng phải lớn hơn 0.",
                ephemeral=True
            )
            return

        stock = int(
            product.get("stock", 0)
        )

        if quantity > stock:
            await interaction.response.send_message(
                f"❌ Kho chỉ còn **{stock}** sản phẩm.",
                ephemeral=True
            )
            return

        price = int(
            product.get("price", 0)
        )

        total = price * quantity

        embed = discord.Embed(
            title="📋 XÁC NHẬN ĐƠN HÀNG",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="📦 Sản phẩm",
            value=product.get(
                "name",
                self.product_id
            ),
            inline=False
        )

        embed.add_field(
            name="🔢 Số lượng",
            value=str(quantity),
            inline=True
        )

        embed.add_field(
            name="💰 Đơn giá",
            value=money(price),
            inline=True
        )

        embed.add_field(
            name="💵 TỔNG TIỀN",
            value=f"**{money(total)}**",
            inline=False
        )

        embed.add_field(
            name="📦 Kho hiện tại",
            value=str(stock),
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmOrderView(
                self.product_id,
                quantity,
                price,
                total
            ),
            ephemeral=True
        )


# =========================================================
# XÁC NHẬN ĐƠN
# =========================================================

class ConfirmOrderView(discord.ui.View):

    def __init__(
        self,
        product_id,
        quantity,
        price,
        total
    ):

        super().__init__(timeout=300)

        self.product_id = product_id
        self.quantity = quantity
        self.price = price
        self.total = total

    @discord.ui.button(
        label="Xác nhận đơn",
        emoji="✅",
        style=discord.ButtonStyle.success
    )
    async def confirm(
        self,
        interaction,
        button
    ):

        guild = interaction.guild
        user = interaction.user

        if not guild:
            return

        if not isinstance(
            user,
            discord.Member
        ):
            return

        # Kiểm tra ticket đang mở
        old_ticket = find_open_ticket(
            guild,
            user.id
        )

        if old_ticket:
            await interaction.response.edit_message(
                content=(
                    f"❌ Bạn đang có ticket: "
                    f"{old_ticket.mention}"
                ),
                embed=None,
                view=None
            )
            return

        product = products.get(
            self.product_id
        )

        if not product:
            await interaction.response.edit_message(
                content="❌ Sản phẩm không còn tồn tại.",
                embed=None,
                view=None
            )
            return

        stock = int(
            product.get("stock", 0)
        )

        # Kiểm tra kho lần cuối
        if self.quantity > stock:
            await interaction.response.edit_message(
                content=(
                    f"❌ Không đủ hàng.\n"
                    f"Kho hiện còn: **{stock}**"
                ),
                embed=None,
                view=None
            )
            return

        category = guild.get_channel(
            TICKET_CATEGORY_ID
        )

        if not isinstance(
            category,
            discord.CategoryChannel
        ):
            await interaction.response.edit_message(
                content=(
                    "❌ Không tìm thấy Category ticket.\n"
                    f"ID: `{TICKET_CATEGORY_ID}`"
                ),
                embed=None,
                view=None
            )
            return

        staff_roles = get_staff_roles(guild)

        if not staff_roles:
            await interaction.response.edit_message(
                content=(
                    "❌ Không tìm thấy role nhân viên."
                ),
                embed=None,
                view=None
            )
            return

        # =================================================
        # PERMISSION TICKET
        # =================================================

        overwrites = {
            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )
        }

        for role in staff_roles:

            overwrites[role] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                    attach_files=True,
                    embed_links=True
                )
            )

        # =================================================
        # TÊN TICKET
        # =================================================

        clean_name = re.sub(
            r"[^a-zA-Z0-9_-]",
            "",
            user.name.lower()
        )

        if not clean_name:
            clean_name = "user"

        channel_name = (
            f"order-{clean_name}"
        )[:90]

        # =================================================
        # TẠO TICKET
        # =================================================

        try:

            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Shop Order | User {user.id}"
            )

        except discord.Forbidden:

            await interaction.response.edit_message(
                content=(
                    "❌ Bot không có quyền tạo kênh.\n\n"
                    "Hãy cấp cho bot quyền:\n"
                    "• Manage Channels\n"
                    "• View Channels\n"
                    "• Send Messages"
                ),
                embed=None,
                view=None
            )
            return

        except discord.HTTPException as error:

            print(
                f"❌ Lỗi tạo ticket: {error}"
            )

            await interaction.response.edit_message(
                content="❌ Discord API đang lỗi.",
                embed=None,
                view=None
            )
            return

        # =================================================
        # TRỪ KHO
        # =================================================

        product["stock"] = (
            stock - self.quantity
        )

        product["available"] = (
            product["stock"] > 0
        )

        save_json(
            PRODUCT_FILE,
            products
        )

        # =================================================
        # LƯU TICKET
        # =================================================

        tickets[str(channel.id)] = {

            "user_id": user.id,

            "product_id": self.product_id,

            "product_name": product.get(
                "name",
                self.product_id
            ),

            "quantity": self.quantity,

            "price": self.price,

            "total": self.total,

            "status": "open",

            "created_at":
                datetime.utcnow().isoformat()
        }

        save_json(
            TICKET_FILE,
            tickets
        )

        # =================================================
        # PING STAFF
        # =================================================

        staff_mentions = " ".join(
            role.mention
            for role in staff_roles
        )

        # =================================================
        # TICKET EMBED
        # =================================================

        embed = discord.Embed(
            title="🛒 ĐƠN HÀNG MỚI",
            description=(
                "Đơn hàng đã được xác nhận.\n"
                "Nhân viên vui lòng hỗ trợ khách hàng."
            ),
            color=discord.Color.green()
        )

        embed.add_field(
            name="👤 Khách hàng",
            value=user.mention,
            inline=False
        )

        embed.add_field(
            name="📦 Sản phẩm",
            value=product.get(
                "name",
                self.product_id
            ),
            inline=False
        )

        embed.add_field(
            name="🔢 Số lượng",
            value=str(self.quantity),
            inline=True
        )

        embed.add_field(
            name="💰 Đơn giá",
            value=money(self.price),
            inline=True
        )

        embed.add_field(
            name="💵 TỔNG TIỀN",
            value=f"**{money(self.total)}**",
            inline=False
        )

        embed.add_field(
            name="📦 Kho còn",
            value=str(
                stock - self.quantity
            ),
            inline=True
        )

        embed.add_field(
            name="🆔 Mã sản phẩm",
            value=f"`{self.product_id}`",
            inline=True
        )

        embed.set_footer(
            text="Shop Order System"
        )

        try:

            await channel.send(
                content=(
                    f"{user.mention}\n"
                    f"{staff_mentions}"
                ),
                embed=embed,
                view=TicketView()
            )

        except Exception as error:

            print(
                f"❌ Lỗi gửi ticket: {error}"
            )

        # =================================================
        # THÔNG BÁO KHÁCH
        # =================================================

        await interaction.response.edit_message(
            content=(
                "✅ **ĐẶT HÀNG THÀNH CÔNG!**\n\n"
                f"🎫 Ticket: {channel.mention}\n"
                f"📦 Sản phẩm: **{product.get('name')}**\n"
                f"🔢 Số lượng: **{self.quantity}**\n"
                f"💵 Tổng tiền: **{money(self.total)}**"
            ),
            embed=None,
            view=None
        )

        # Cập nhật shop
        await update_shop(guild)

    @discord.ui.button(
        label="Hủy đơn",
        emoji="❌",
        style=discord.ButtonStyle.danger
    )
    async def cancel(
        self,
        interaction,
        button
    ):

        await interaction.response.edit_message(
            content="❌ Đã hủy đơn hàng.",
            embed=None,
            view=None
        )


# =========================================================
# TICKET VIEW
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button
