import os
import json
import re
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import app_commands


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("TOKEN")

SHOP_CHANNEL_ID = 1545458090789576723

TICKET_CATEGORY_ID = 1545458506755473458

STAFF_ROLE_IDS = {
    1537485808229949483,
    1537485814676848690,
    1537485810570498179,
}

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
# DATA
# =========================================================

products = {}
tickets = {}


def load_data(filename, default):
    if not os.path.exists(filename):
        return default

    try:
        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        return data

    except Exception as error:
        print(
            f"[DATA] Không đọc được {filename}: {error}"
        )
        return default


def save_data(filename, data):
    try:
        with open(
            filename,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=4
            )

    except Exception as error:
        print(
            f"[DATA] Không lưu được {filename}: {error}"
        )


# =========================================================
# UTIL
# =========================================================

def format_money(value):
    return f"{int(value):,}".replace(",", ".") + " VNĐ"


def parse_price(value):
    text = str(value).strip().lower()

    text = text.replace(" ", "")

    if text.endswith("k"):
        try:
            return int(float(text[:-1]) * 1000)
        except ValueError:
            return 0

    if text.endswith("m"):
        try:
            return int(float(text[:-1]) * 1000000)
        except ValueError:
            return 0

    text = text.replace(".", "")
    text = text.replace(",", "")

    numbers = re.sub(r"\D", "", text)

    if not numbers:
        return 0

    return int(numbers)


def is_staff(member):
    if member.guild_permissions.administrator:
        return True

    for role in member.roles:
        if role.id in STAFF_ROLE_IDS:
            return True

    return False


def get_staff_roles(guild):
    roles = []

    for role_id in STAFF_ROLE_IDS:
        role = guild.get_role(role_id)

        if role is not None:
            roles.append(role)

    return roles


def get_existing_ticket(guild, user_id):
    for channel_id, data in tickets.items():

        if data.get("user_id") != user_id:
            continue

        if data.get("status") != "open":
            continue

        channel = guild.get_channel(
            int(channel_id)
        )

        if isinstance(channel, discord.TextChannel):
            return channel

    return None


# =========================================================
# SHOP EMBED
# =========================================================

def create_shop_embed():

    embed = discord.Embed(
        title="🛍️ SHOP ONLINE",
        description=(
            "Chào mừng bạn đến với shop!\n\n"
            "🛒 **1.** Chọn sản phẩm\n"
            "🔢 **2.** Nhập số lượng\n"
            "📋 **3.** Kiểm tra đơn hàng\n"
            "✅ **4.** Xác nhận đơn\n"
            "🎫 **5.** Ticket được tạo tự động\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 Giá và kho được cập nhật tự động."
        ),
        color=discord.Color.gold()
    )

    count = 0

    for code, product in products.items():

        stock = int(
            product.get("stock", 0)
        )

        name = product.get(
            "name",
            code
        )

        price = int(
            product.get("price", 0)
        )

        description = product.get(
            "description",
            ""
        )

        if stock <= 0:
            status = "🔴 Hết hàng"
        else:
            status = f"🟢 Còn **{stock}**"

        value = (
            f"💰 **{format_money(price)}**\n"
            f"📦 {status}"
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

        count += 1

        if count >= 25:
            break

    if count == 0:
        embed.add_field(
            name="📦 Sản phẩm",
            value="🔴 Shop hiện chưa có sản phẩm.",
            inline=False
        )

    embed.set_footer(
        text="Shop System"
    )

    return embed


# =========================================================
# PRODUCT SELECT
# =========================================================

class ProductSelect(discord.ui.Select):

    def __init__(self):

        options = []

        for code, product in products.items():

            stock = int(
                product.get("stock", 0)
            )

            if stock <= 0:
                continue

            name = str(
                product.get("name", code)
            )[:100]

            price = int(
                product.get("price", 0)
            )

            options.append(
                discord.SelectOption(
                    label=name,
                    description=(
                        f"{format_money(price)} | "
                        f"Kho {stock}"
                    )[:100],
                    value=code,
                    emoji="📦"
                )
            )

            if len(options) >= 25:
                break

        if not options:
            options.append(
                discord.SelectOption(
                    label="Shop đang hết hàng",
                    description="Chưa có sản phẩm khả dụng",
                    value="EMPTY",
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

        code = self.values[0]

        if code == "EMPTY":
            await interaction.response.send_message(
                "❌ Hiện shop chưa có sản phẩm.",
                ephemeral=True
            )
            return

        product = products.get(code)

        if product is None:
            await interaction.response.send_message(
                "❌ Sản phẩm không tồn tại.",
                ephemeral=True
            )
            return

        if int(product.get("stock", 0)) <= 0:
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

class ShopView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ProductSelect())


# =========================================================
# QUANTITY MODAL
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

    async def on_submit(self, interaction):

        product = products.get(self.code)

        if product is None:
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
                f"❌ Kho chỉ còn **{stock}**.",
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
            value=format_money(price),
            inline=True
        )

        embed.add_field(
            name="💵 Tổng tiền",
            value=f"**{format_money(total)}**",
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
                self.code,
                quantity,
                price,
                total
            ),
            ephemeral=True
        )


# =========================================================
# CONFIRM ORDER VIEW
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
        super().__init__(timeout=300)

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
        interaction,
        button
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

        existing = get_existing_ticket(
            guild,
            user.id
        )

        if existing is not None:

            await interaction.response.edit_message(
                content=(
                    "❌ Bạn đang có ticket:\n"
                    f"{existing.mention}"
                ),
                embed=None,
                view=None
            )

            return

        product = products.get(
            self.code
        )

        if product is None:

            await interaction.response.edit_message(
                content="❌ Sản phẩm không còn tồn tại.",
                embed=None,
                view=None
            )

            return

        stock = int(
            product.get("stock", 0)
        )

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

        staff_roles = get_staff_roles(
            guild
        )

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
        # PERMISSIONS
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

        username = re.sub(
            r"[^a-zA-Z0-9-]",
            "",
            user.name
        ).lower()

        if not username:
            username = "user"

        username = username[:70]

        channel_name = (
            f"order-{username}"
        )

        # =================================================
        # CREATE CHANNEL
        # =================================================

        try:

            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=(
                    f"Shop Order | "
                    f"User ID: {user.id}"
                )
            )

        except discord.Forbidden:

            await interaction.response.edit_message(
                content=(
                    "❌ Bot không có quyền tạo ticket.\n\n"
                    "Cần cấp cho bot:\n"
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
                f"[CREATE TICKET] {error}"
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

        save_data(
            PRODUCT_FILE,
            products
        )

        # =================================================
        # SAVE TICKET
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

        save_data(
            TICKET_FILE,
            tickets
        )

        # =================================================
        # STAFF MENTION
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
                "Nhân viên hãy hỗ trợ khách hàng."
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
            value=format_money(self.price),
            inline=True
        )

        embed.add_field(
            name="💵 TỔNG TIỀN",
            value=f"**{format_money(self.total)}**",
            inline=False
        )

        embed.add_field(
            name="📦 Kho còn lại",
            value=str(product["stock"]),
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

        except discord.HTTPException as error:

            print(
                f"[TICKET MESSAGE] {error}"
            )

        # =================================================
        # RESPONSE
        # =================================================

        await interaction.response.edit_message(
            content=(
                "✅ **ĐẶT HÀNG THÀNH CÔNG!**\n\n"
                f"🎫 Ticket: {channel.mention}\n"
                f"📦 Sản phẩm: "
                f"**{product.get('name', self.code)}**\n"
                f"🔢 Số lượng: "
                f"**{self.quantity}**\n"
                f"💵 Tổng tiền: "
                f"**{format_money(self.total)}**"
            ),
            embed=None,
            view=None
        )

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

class TicketView(
    discord.ui.View
):

    def __init__(self):
        super().__init
