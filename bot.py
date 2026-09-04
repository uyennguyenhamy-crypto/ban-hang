import os
import json
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import app_commands


# =========================================================
# CẤU HÌNH
# =========================================================

TOKEN = os.getenv("TOKEN")

# Kênh chứa bảng SHOP
SHOP_CHANNEL_ID = 1545458090789576723

# Category chứa các ticket
TICKET_CATEGORY_ID = 1545458506755473458

# Role nhân viên
STAFF_ROLE_IDS = {
    1537485808229949483,
    1537485814676848690,
    1537485810570498179,
}

# File dữ liệu
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

products = {}
tickets = {}


def load_json(path, default):
    if not os.path.exists(path):
        return default

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if isinstance(data, type(default)):
            return data

    except (
        OSError,
        json.JSONDecodeError
    ) as error:

        print(
            f"[DATABASE] Không đọc được {path}: {error}"
        )

    return default


def save_json(path, data):

    temp_path = f"{path}.tmp"

    try:

        with open(
            temp_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_path,
            path
        )

    except OSError as error:

        print(
            f"[DATABASE] Không lưu được {path}: {error}"
        )


# =========================================================
# TIỆN ÍCH
# =========================================================

def money(value):

    return (
        f"{int(value):,}"
        .replace(",", ".")
        + " VNĐ"
    )


def parse_price(value):

    text = (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
    )

    multiplier = 1

    if text.endswith("k"):

        multiplier = 1000
        text = text[:-1]

    elif text.endswith("m"):

        multiplier = 1_000_000
        text = text[:-1]

    text = (
        text
        .replace(".", "")
        .replace(",", "")
    )

    digits = re.sub(
        r"\D",
        "",
        text
    )

    if not digits:
        return 0

    return int(digits) * multiplier


def is_staff(member: discord.Member):

    if member.guild_permissions.administrator:
        return True

    return any(
        role.id in STAFF_ROLE_IDS
        for role in member.roles
    )


def get_staff_roles(guild: discord.Guild):

    result = []

    for role_id in STAFF_ROLE_IDS:

        role = guild.get_role(
            role_id
        )

        if role is not None:
            result.append(role)

    return result


def get_open_ticket(
    guild: discord.Guild,
    user_id: int
):

    for channel_id, data in tickets.items():

        if data.get("user_id") != user_id:
            continue

        if data.get("status") != "open":
            continue

        channel = guild.get_channel(
            int(channel_id)
        )

        if isinstance(
            channel,
            discord.TextChannel
        ):
            return channel

    return None


# =========================================================
# SHOP EMBED
# =========================================================

def make_shop_embed():

    embed = discord.Embed(
        title="🛍️ SHOP ONLINE",

        description=(
            "Chào mừng bạn đến với shop!\n\n"

            "🛒 **Bước 1:** Chọn sản phẩm\n"
            "🔢 **Bước 2:** Nhập số lượng\n"
            "📋 **Bước 3:** Kiểm tra đơn hàng\n"
            "✅ **Bước 4:** Xác nhận\n"
            "🎫 **Bước 5:** Ticket được tạo tự động\n\n"

            "━━━━━━━━━━━━━━━━━━━━\n"

            "💡 Giá và số lượng được cập nhật tự động."
        ),

        color=discord.Color.gold()
    )

    available = 0

    for code, product in products.items():

        stock = int(
            product.get(
                "stock",
                0
            )
        )

        if stock <= 0:
            continue

        available += 1

        name = product.get(
            "name",
            code
        )

        price = int(
            product.get(
                "price",
                0
            )
        )

        description = (
            product
            .get(
                "description",
                ""
            )
            .strip()
        )

        value = (
            f"💰 **{money(price)}**\n"
            f"📦 Kho: **{stock}**"
        )

        if description:

            value += (
                f"\n📝 {description[:150]}"
            )

        embed.add_field(
            name=f"📦 {name}",
            value=value,
            inline=True
        )

        if available >= 25:
            break

    if available == 0:

        embed.add_field(
            name="📦 Sản phẩm",
            value=(
                "🔴 Hiện chưa có sản phẩm còn hàng."
            ),
            inline=False
        )

    embed.set_footer(
        text="Shop System • Chọn sản phẩm để mua"
    )

    return embed


# =========================================================
# CHỌN SẢN PHẨM
# =========================================================

class ProductSelect(
    discord.ui.Select
):

    def __init__(self):

        options = []

        for code, product in products.items():

            stock = int(
                product.get(
                    "stock",
                    0
                )
            )

            if stock <= 0:
                continue

            name = str(
                product.get(
                    "name",
                    code
                )
            )[:100]

            price = int(
                product.get(
                    "price",
                    0
                )
            )

            options.append(
                discord.SelectOption(
                    label=name,
                    description=(
                        f"{money(price)} • Kho {stock}"
                    )[:100],
                    value=code,
                    emoji="📦"
                )
            )

            if len(options) >= 25:
                break

        if not options:

            options = [
                discord.SelectOption(
                    label="Shop chưa có hàng",
                    description=(
                        "Hiện không có sản phẩm còn hàng"
                    ),
                    value="__empty__",
                    emoji="❌"
                )
            ]

        super().__init__(
            placeholder="🛒 Chọn sản phẩm...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="shop_product_select"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        code = self.values[0]

        if code == "__empty__":

            await interaction.response.send_message(
                "❌ Hiện không có sản phẩm còn hàng.",
                ephemeral=True
            )

            return

        product = products.get(code)

        if not product:

            await interaction.response.send_message(
                "❌ Sản phẩm không còn tồn tại.",
                ephemeral=True
            )

            return

        if int(
            product.get(
                "stock",
                0
            )
        ) <= 0:

            await interaction.response.send_message(
                "❌ Sản phẩm vừa hết hàng.",
                ephemeral=True
            )

            return

        await interaction.response.send_modal(
            QuantityModal(code)
        )


# =========================================================
# SHOP VIEW
# =========================================================

class ShopView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            ProductSelect()
        )


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
        max_length=6,
        required=True
    )

    def __init__(self, code):

        super().__init__()

        self.code = code

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        product = products.get(
            self.code
        )

        if not product:

            await interaction.response.send_message(
                "❌ Sản phẩm không tồn tại.",
                ephemeral=True
            )

            return

        try:

            quantity = int(
                self.quantity.value.strip()
            )

        except ValueError:

            await interaction.response.send_message(
                "❌ Số lượng phải là số nguyên.",
                ephemeral=True
            )

            return

        stock = int(
            product.get(
                "stock",
                0
            )
        )

        if quantity <= 0:

            await interaction.response.send_message(
                "❌ Số lượng phải lớn hơn 0.",
                ephemeral=True
            )

            return

        if quantity > stock:

            await interaction.response.send_message(
                f"❌ Kho chỉ còn **{stock}** sản phẩm.",
                ephemeral=True
            )

            return

        price = int(
            product.get(
                "price",
                0
            )
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
                self.code
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
            name="💵 Tổng tiền",
            value=f"**{money(total)}**",
            inline=False
        )

        embed.add_field(
            name="📦 Kho",
            value=str(stock),
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmOrderView(
                self.code,
                quantity,
                price,
                total
            ),
            ephemeral=True
        )


# =========================================================
# XÁC NHẬN ĐƠN
# =========================================================

class ConfirmOrderView(
    discord.ui.View
):

    def __init__(
        self,
        code,
        quantity,
        price,
        total
    ):

        super().__init__(
            timeout=300
        )

        self.code = code
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
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild
        user = interaction.user

        if guild is None:
            return

        if not isinstance(
            user,
            discord.Member
        ):
            return

        # Không cho một người mở nhiều ticket
        existing = get_open_ticket(
            guild,
            user.id
        )

        if existing:

            await interaction.response.edit_message(
                content=(
                    f"❌ Bạn đang có ticket: "
                    f"{existing.mention}"
                ),
                embed=None,
                view=None
            )

            return

        product = products.get(
            self.code
        )

        if not product:

            await interaction.response.edit_message(
                content="❌ Sản phẩm không còn tồn tại.",
                embed=None,
                view=None
            )

            return

        stock = int(
            product.get(
                "stock",
                0
            )
        )

        # Kiểm tra kho lần cuối
        if self.quantity > stock:

            await interaction.response.edit_message(
                content=(
                    f"❌ Kho hiện chỉ còn **{stock}**."
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

        roles = get_staff_roles(
            guild
        )

        if not roles:

            await interaction.response.edit_message(
                content="❌ Không tìm thấy role nhân viên.",
                embed=None,
                view=None
            )

            return

        # =================================================
        # QUYỀN TICKET
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

        for role in roles:

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

        safe_name = re.sub(
            r"[^a-z0-9-]",
            "",
            user.name.lower()
        )

        if not safe_name:
            safe_name = "user"

        safe_name = safe_name[:70]

        channel_name = (
            f"order-{safe_name}"
        )

        # =================================================
        # TẠO TICKET
        # =================================================

        try:

            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=(
                    f"Shop order • User {user.id}"
                )
            )

        except discord.Forbidden:

            await interaction.response.edit_message(
                content=(
                    "❌ Bot thiếu quyền tạo kênh.\n\n"
                    "Hãy cấp cho bot:\n"
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
                f"[TICKET] Create error: {error}"
            )

            await interaction.response.edit_message(
                content=(
                    "❌ Discord không cho tạo ticket."
                ),
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

            "product_id": self.code,

            "product_name": product.get(
                "name",
                self.code
            ),

            "quantity": self.quantity,

            "price": self.price,

            "total": self.total,

            "status": "open",

            "created_at":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }

        save_json(
            TICKET_FILE,
            tickets
        )

        # =================================================
        # PING NHÂN VIÊN
        # =================================================

        staff_mentions = " ".join(
            role.mention
            for role in roles
        )

        # =================================================
        # EMBED TICKET
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
                self.code
            ),
            inline=False
        )

        embed.add_field(
            name="🆔 Mã sản phẩm",
            value=f"`{self.code}`",
            inline=True
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
            name="📦 Kho còn lại",
            value=str(
                product["stock"]
            ),
            inline=True
        )

        embed.set_footer(
            text="Shop Order System"
        )

        try:

            await channel.send(
                content=(
                    f"{user.mention} "
                    f"{staff_mentions}"
                ),
                embed=embed,
                view=TicketView()
            )

        except discord.HTTP
