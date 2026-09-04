import os
import json
import asyncio
import re
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("TOKEN")

# Kênh hiển thị shop
SHOP_CHANNEL_ID = 1545458090789576723

# Category tạo ticket
TICKET_CATEGORY_ID = 1545458506755473458

# Role nhân viên
STAFF_ROLE_IDS = [
    1537485808229949483,
    1537485814676848690,
    1537485810570498179,
]

PRODUCTS_FILE = "products.json"
TICKETS_FILE = "tickets.json"


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="?",
    intents=intents,
    help_command=None,
)


# =========================================================
# DATABASE
# =========================================================

def load_json(filename):
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except Exception as error:
        print(f"❌ Không thể đọc {filename}: {error}")

    return {}


def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False,
            )
    except Exception as error:
        print(f"❌ Không thể lưu {filename}: {error}")


products = load_json(PRODUCTS_FILE)
tickets = load_json(TICKETS_FILE)


# =========================================================
# PRICE
# =========================================================

def parse_price(value):
    """
    Hỗ trợ:
    50000
    "50000"
    "50.000"
    "50,000"
    "50k"
    "50 K"
    """

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    text = str(value).strip().lower()
    text = text.replace(" ", "")

    multiplier = 1

    if text.endswith("k"):
        multiplier = 1000
        text = text[:-1]

    text = text.replace(".", "")
    text = text.replace(",", "")

    numbers = re.sub(r"[^\d]", "", text)

    if not numbers:
        return 0

    return int(numbers) * multiplier


def format_money(value):
    try:
        value = int(value)
    except Exception:
        value = parse_price(value)

    return f"{value:,}".replace(",", ".") + " VNĐ"


# =========================================================
# STAFF
# =========================================================

def is_staff(member: discord.Member):
    if member.guild_permissions.administrator:
        return True

    return any(
        role.id in STAFF_ROLE_IDS
        for role in member.roles
    )


# =========================================================
# ERROR RESPONSE
# =========================================================

async def interaction_error(
    interaction: discord.Interaction,
    message: str,
):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                message,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )
    except discord.HTTPException:
        pass


# =========================================================
# TÌM TICKET USER
# =========================================================

def find_user_ticket(guild, user_id):

    for channel_id, data in tickets.items():

        if data.get("user_id") != user_id:
            continue

        channel = guild.get_channel(
            int(channel_id)
        )

        if channel:
            return channel

    return None


# =========================================================
# SHOP SELECT
# =========================================================

class ProductSelect(
    discord.ui.Select
):

    def __init__(self):

        options = []

        available_products = []

        for product_id, product in products.items():

            stock = int(
                product.get("stock", 0)
            )

            if stock <= 0:
                continue

            available_products.append(
                (product_id, product)
            )

        # Discord Select tối đa 25 option
        available_products = available_products[:25]

        for product_id, product in available_products:

            price = parse_price(
                product.get("price", 0)
            )

            stock = int(
                product.get("stock", 0)
            )

            description = (
                f"{format_money(price)} | Kho: {stock}"
            )

            description = description[:100]

            options.append(
                discord.SelectOption(
                    label=str(
                        product.get(
                            "name",
                            product_id
                        )
                    )[:100],
                    description=description,
                    value=product_id,
                    emoji="📦",
                )
            )

        if not options:

            options.append(
                discord.SelectOption(
                    label="Hiện chưa có sản phẩm",
                    description="Shop đang hết hàng",
                    value="no_product",
                    emoji="❌",
                )
            )

        super().__init__(
            placeholder="🛒 Chọn sản phẩm muốn mua...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="shop_product_select",
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):

        product_id = self.values[0]

        if product_id == "no_product":

            await interaction.response.send_message(
                "❌ Hiện chưa có sản phẩm còn hàng.",
                ephemeral=True,
            )
            return

        product = products.get(product_id)

        if product is None:

            await interaction.response.send_message(
                "❌ Sản phẩm không còn tồn tại.",
                ephemeral=True,
            )
            return

        stock = int(
            product.get("stock", 0)
        )

        if stock <= 0:

            await interaction.response.send_message(
                "❌ Sản phẩm đã hết hàng.",
                ephemeral=True,
            )
            return

        modal = QuantityModal(
            product_id=product_id
        )

        await interaction.response.send_modal(
            modal
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
    title="🛒 Nhập số lượng",
):

    quantity = discord.ui.TextInput(
        label="Số lượng",
        placeholder="Ví dụ: 1",
        required=True,
        min_length=1,
        max_length=5,
    )

    def __init__(self, product_id):

        super().__init__()

        self.product_id = product_id

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        product = products.get(
            self.product_id
        )

        if product is None:

            await interaction.response.send_message(
                "❌ Sản phẩm không tồn tại.",
                ephemeral=True,
            )
            return

        try:
            quantity = int(
                self.quantity.value
            )
        except ValueError:

            await interaction.response.send_message(
                "❌ Số lượng phải là số.",
                ephemeral=True,
            )
            return

        if quantity <= 0:

            await interaction.response.send_message(
                "❌ Số lượng phải lớn hơn 0.",
                ephemeral=True,
            )
            return

        stock = int(
            product.get("stock", 0)
        )

        if quantity > stock:

            await interaction.response.send_message(
                f"❌ Kho chỉ còn **{stock}** sản phẩm.",
                ephemeral=True,
            )
            return

        price = parse_price(
            product.get("price", 0)
        )

        total = price * quantity

        embed = discord.Embed(
            title="📋 XÁC NHẬN ĐƠN HÀNG",
            color=discord.Color.gold(),
        )

        embed.add_field(
            name="📦 Sản phẩm",
            value=product.get(
                "name",
                self.product_id
            ),
            inline=False,
        )

        embed.add_field(
            name="🔢 Số lượng",
            value=str(quantity),
            inline=True,
        )

        embed.add_field(
            name="💰 Đơn giá",
            value=format_money(price),
            inline=True,
        )

        embed.add_field(
            name="💵 Tổng tiền",
            value=f"**{format_money(total)}**",
            inline=False,
        )

        embed.add_field(
            name="📦 Kho còn lại",
            value=str(stock - quantity),
            inline=True,
        )

        embed.set_footer(
            text="Kiểm tra kỹ đơn hàng trước khi xác nhận."
        )

        view = ConfirmOrderView(
            product_id=self.product_id,
            quantity=quantity,
            price=price,
            total=total,
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )


# =========================================================
# XÁC NHẬN ĐƠN
# =========================================================

class ConfirmOrderView(
    discord.ui.View
):

    def __init__(
        self,
        product_id,
        quantity,
        price,
        total,
    ):

        super().__init__(
            timeout=300
        )

        self.product_id = product_id
        self.quantity = quantity
        self.price = price
        self.total = total

    @discord.ui.button(
        label="Xác nhận đơn",
        emoji="✅",
        style=discord.ButtonStyle.success,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        product = products.get(
            self.product_id
        )

        if product is None:

            await interaction.response.edit_message(
                content="❌ Sản phẩm không còn tồn tại.",
                embed=None,
                view=None,
            )
            return

        stock = int(
            product.get("stock", 0)
        )

        # Kiểm tra lại kho ngay lúc xác nhận
        if self.quantity > stock:

            await interaction.response.edit_message(
                content=(
                    f"❌ Không đủ hàng. "
                    f"Kho hiện còn **{stock}**."
                ),
                embed=None,
                view=None,
            )
            return

        guild = interaction.guild
        user = interaction.user

        if guild is None:
            return

        if not isinstance(
            user,
            discord.Member
        ):
            return

        old_ticket = find_user_ticket(
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
                view=None,
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
                content="❌ Category ticket không tồn tại.",
                embed=None,
                view=None,
            )
            return

        # =================================================
        # STAFF
        # =================================================

        staff_roles = []

        for role_id in STAFF_ROLE_IDS:

            role = guild.get_role(
                role_id
            )

            if role:
                staff_roles.append(role)

        if not staff_roles:

            await interaction.response.edit_message(
                content="❌ Không tìm thấy role nhân viên.",
                embed=None,
                view=None,
            )
            return

        # =================================================
        # PERMISSION
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
                    embed_links=True,
                ),
        }

        for role in staff_roles:

            overwrites[role] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                    manage_messages=True,
                    attach_files=True,
                    embed_links=True,
                )
            )

        # =================================================
        # TICKET NAME
        # =================================================

        username = re.sub(
            r"[^a-zA-Z0-9_-]",
            "",
            user.name.lower()
        )

        if not username:
            username = "user"

        channel_name = (
            f"order-{username}"
        )[:90]

        # =================================================
        # CREATE CHANNEL
        # =================================================

        try:

            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=(
                    f"order-owner:{user.id}"
                    f"|product:{self.product_id}"
                ),
                reason="Shop order ticket",
            )

        except discord.Forbidden:

            await interaction.response.edit_message(
                content=(
                    "❌ Bot không có quyền tạo ticket."
                ),
                embed=None,
                view=None,
            )
            return

        except discord.HTTPException as error:

            print(
                f"❌ Discord API error: {error}"
            )

            await interaction.response.edit_message(
                content="❌ Discord đang gặp lỗi.",
                embed=None,
                view=None,
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
            PRODUCTS_FILE,
            products
        )

        # =================================================
        # SAVE TICKET
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
                datetime.utcnow().isoformat(),
        }

        save_json(
            TICKETS_FILE,
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
                "Nhân viên vui lòng hỗ trợ khách hàng."
            ),
            color=discord.Color.green(),
        )

        embed.add_field(
            name="👤 Khách hàng",
            value=user.mention,
            inline=False,
        )

        embed.add_field(
            name="📦 Sản phẩm",
            value=product.get(
                "name",
                self.product_id
            ),
            inline=False,
        )

        embed.add_field(
            name="🔢 Số lượng",
            value=str(self.quantity),
            inline=True,
        )

        embed.add_field(
            name="💰 Đơn giá",
            value=format_money(self.price),
            inline=True,
        )

        embed.add_field(
            name="💵 TỔNG TIỀN",
            value=f"**{format_money(self.total)}**",
            inline=False,
        )

        embed.add_field(
            name="📊 Kho sau đơn",
            value=str(
                stock - self.quantity
            ),
            inline=True,
        )

        embed.add_field(
            name="🆔 Mã sản phẩm",
            value=f"`{self.product_id}`",
            inline=True,
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
                view=TicketControlView(),
            )

        except Exception as error:

            print(
                f"❌ Không thể gửi ticket: {error}"
            )

        # =================================================
        # RESPONSE
        # =================================================

        await interaction.response.edit_message(
            content=(
                f"✅ **Đặt hàng thành công!**\n\n"
                f"🎫 Ticket: {channel.mention}\n"
                f"📦 {product.get('name')}\n"
                f"🔢 Số lượng: {self.quantity}\n"
                f"💵 Tổng: **{format_money(self.total)}**"
            ),
            embed=None,
            view=None,
        )

        # =================================================
        # UPDATE SHOP
        # =================================================

        await refresh_shop_panel(guild)


    @discord.ui.button(
        label="Hủy",
        emoji="❌",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await interaction.response.ed
