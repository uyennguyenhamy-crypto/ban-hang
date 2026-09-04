import os
import json
import asyncio
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("TOKEN")

# Kênh hiển thị bảng mua hàng / ticket
SHOP_CHANNEL_ID = 1545458090789576723

# Category chứa ticket
TICKET_CATEGORY_ID = 1545458506755473458

# 3 role nhân viên
STAFF_ROLE_IDS = [
    1537485808229949483,
    1537485814676848690,
    1537485810570498179
]

TICKETS_FILE = "tickets.json"
PRODUCTS_FILE = "products.json"


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
    help_command=None
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

        return data if isinstance(data, dict) else {}

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

        print(
            f"❌ Lỗi lưu {filename}: {e}"
        )


tickets = load_json(TICKETS_FILE)
products = load_json(PRODUCTS_FILE)


# =========================================================
# PERMISSION
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

async def send_error(
    interaction: discord.Interaction,
    message: str
):

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                message,
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                message,
                ephemeral=True
            )

    except discord.HTTPException:
        pass


# =========================================================
# TICKET CHECK
# =========================================================

def find_user_ticket(
    guild,
    user_id
):

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
# NÚT TẠO TICKET
# =========================================================

class TicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Tạo Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.success,
        custom_id="shop_create_ticket"
    )
    async def create_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        try:

            guild = interaction.guild
            user = interaction.user

            if guild is None:
                await send_error(
                    interaction,
                    "❌ Không xác định được server."
                )
                return

            if not isinstance(
                user,
                discord.Member
            ):
                return

            category = guild.get_channel(
                TICKET_CATEGORY_ID
            )

            if not isinstance(
                category,
                discord.CategoryChannel
            ):

                await send_error(
                    interaction,
                    "❌ Category ticket không tồn tại."
                )
                return

            old_ticket = find_user_ticket(
                guild,
                user.id
            )

            if old_ticket:

                await send_error(
                    interaction,
                    f"❌ Bạn đã có ticket: "
                    f"{old_ticket.mention}"
                )
                return

            staff_roles = []

            for role_id in STAFF_ROLE_IDS:

                role = guild.get_role(role_id)

                if role:
                    staff_roles.append(role)

            if not staff_roles:

                await send_error(
                    interaction,
                    "❌ Không tìm thấy role nhân viên."
                )
                return

            safe_name = "".join(
                c
                for c in user.name.lower()
                if c.isalnum() or c in "-_"
            )

            if not safe_name:
                safe_name = "user"

            channel_name = (
                f"ticket-{safe_name}"
            )[:90]

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
                        manage_channels=True,
                        manage_messages=True,
                        attach_files=True,
                        embed_links=True
                    )
                )

            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"ticket-owner:{user.id}"
            )

            tickets[str(channel.id)] = {
                "user_id": user.id,
                "status": "open",
                "created_at": datetime.utcnow().isoformat()
            }

            save_json(
                TICKETS_FILE,
                tickets
            )

            mentions = " ".join(
                role.mention
                for role in staff_roles
            )

            embed = discord.Embed(
                title="🎫 TICKET MUA HÀNG",
                description=(
                    f"Xin chào {user.mention}!\n\n"
                    "Vui lòng gửi thông tin cần mua:\n\n"
                    "📦 **Sản phẩm:**\n"
                    "🔢 **Số lượng:**\n"
                    "💰 **Giá:**\n"
                    "📝 **Yêu cầu:**\n\n"
                    "👨‍💼 Nhân viên sẽ hỗ trợ bạn."
                ),
                color=discord.Color.green()
            )

            embed.set_footer(
                text="Shop Ticket System"
            )

            await channel.send(
                content=(
                    f"{user.mention}\n"
                    f"{mentions}"
                ),
                embed=embed,
                view=TicketControlView()
            )

            await interaction.response.send_message(
                f"✅ Đã tạo ticket: {channel.mention}",
                ephemeral=True
            )

        except discord.Forbidden:

            await send_error(
                interaction,
                "❌ Bot không có đủ quyền."
            )

        except discord.HTTPException as e:

            print(
                f"❌ Discord API: {e}"
            )

            await send_error(
                interaction,
                "❌ Discord đang lỗi. Thử lại sau."
            )

        except Exception as e:

            print(
                f"❌ Ticket error: {e}"
            )

            await send_error(
                interaction,
                "❌ Không thể tạo ticket."
            )


# =========================================================
# NÚT ĐÓNG TICKET
# =========================================================

class TicketControlView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Đóng Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="shop_close_ticket"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        try:

            guild = interaction.guild
            channel = interaction.channel

            if guild is None:
                return

            if not isinstance(
                channel,
                discord.TextChannel
            ):
                return

            data = tickets.get(
                str(channel.id)
            )

            if data is None:

                await send_error(
                    interaction,
                    "❌ Đây không phải ticket."
                )
                return

            user = interaction.user

            if not isinstance(
                user,
                discord.Member
            ):
                return

            if not is_staff(user):

                if data["user_id"] != user.id:

                    await send_error(
                        interaction,
                        "❌ Bạn không có quyền."
                    )
                    return

            if data.get("status") == "closed":

                await send_error(
                    interaction,
                    "🔒 Ticket đã đóng."
                )
                return

            owner = guild.get_member(
                int(data["user_id"])
            )

            if owner:

                await channel.set_permissions(
                    owner,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True
                )

            data["status"] = "closed"
            data["closed_at"] = (
                datetime.utcnow().isoformat()
            )

            save_json(
                TICKETS_FILE,
                tickets
            )

            await interaction.response.send_message(
                "🔒 **Ticket đã được đóng.**"
            )

            await channel.send(
                "🗑️ Nhân viên có thể dùng "
                "`?xoaticket` để xoá ticket."
            )

        except Exception as e:

            print(
                f"❌ Close ticket error: {e}"
            )

            await send_error(
                interaction,
                "❌ Không thể đóng ticket."
            )


# =========================================================
# NÚT MUA SẢN PHẨM
# =========================================================

class ProductBuyView(
    discord.ui.View
):

    def __init__(self, product_id):

        super().__init__(
            timeout=None
        )

        self.product_id = product_id

        button = discord.ui.Button(
            label="Mua hàng",
            emoji="🛒",
            style=discord.ButtonStyle.success,
            custom_id=f"buy_product_{product_id}"
        )

        button.callback = self.buy_product

        self.add_item(button)

    async def buy_product(
        self,
        interaction: discord.Interaction
    ):

        try:

            product = products.get(
                self.product_id
            )

            if product is None:

                await send_error(
                    interaction,
                    "❌ Sản phẩm không tồn tại."
                )
                return

            if not product.get(
                "available",
                True
            ):

                await send_error(
                    interaction,
                    "❌ Sản phẩm hiện đã hết hàng."
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

                await send_error(
                    interaction,
                    f"❌ Bạn đã có ticket: "
                    f"{old_ticket.mention}"
                )
                return

            category = guild.get_channel(
                TICKET_CATEGORY_ID
            )

            if not isinstance(
                category,
                discord.CategoryChannel
            ):

                await send_error(
                    interaction,
                    "❌ Category ticket không tồn tại."
                )
                return

            staff_roles = []

            for role_id in STAFF_ROLE_IDS:

                role = guild.get_role(role_id)

                if role:
                    staff_roles.append(role)

            overwrites = {

                guild.default_role:
                    discord.PermissionOverwrite(
                        view_channel=False
                    ),

                user:
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
            }

            for role in staff_roles:

                overwrites[role] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_channels=True
                    )
                )

            channel = await guild.create_text_channel(
                name=f"mua-{user.name}"[:90],
                category=category,
                overwrites=overwrites,
                topic=(
                    f"ticket-owner:{user.id}"
                    f"|product:{self.product_id}"
                )
            )

            tickets[str(channel.id)] = {
                "user_id": user.id,
                "product_id": self.product_id,
                "product_name": product["name"],
                "status": "open",
                "created_at": datetime.utcnow().isoformat()
            }

            save_json(
                TICKETS_FILE,
                tickets
            )

            staff_mentions = " ".join(
                role.mention
                for role in staff_roles
            )

            embed = discord.Embed(
                title="🛒 ĐƠN HÀNG",
                color=discord.Color.green()
            )

            embed.add_field(
                name="📦 Sản phẩm",
                value=product["name"],
                inline=False
            )

            embed.add_field(
                name="💰 Giá",
                value=product["price"],
                inline=True
            )

            embed.add_field(
                name="📊 Số lượng còn",
                value=str(product["stock"]),
                inline=True
            )

            embed.add_field(
                name="📝 Mô tả",
                value=product.get(
                    "description",
                    "Không có mô tả"
                ),
                inline=False
            )

            embed.add_field(
                name="👤 Khách hàng",
                value=user.mention,
                inline=False
            )

            embed.set_footer(
                text="Shop Ticket System"
            )

            await channel.send(
                content=(
                    f"{user.mention}\n"
                    f"{staff_mentions}"
                ),
                embed=embed,
                view=TicketControlView()
            )

            await interaction.response.send_message(
                f"✅ Đã tạo đơn hàng: {channel.mention}",
                ephemeral=True
            )

        except discord.Forbidden:

            await send_error(
                interaction,
                "❌ Bot không có quyền tạo ticket."
            )

        except discord.HTTPException as e:

            print(
                f"❌ Buy API error: {e}"
            )

            await send_error(
                interaction,
                "❌ Discord đang lỗi."
            )

        except Exception as e:

            print(
                f"❌ Buy error: {e}"
            )

            await send_error(
                interaction,
                "❌ Không thể tạo đơn hàng."
            )


# =========================================================
# /THEMSP
# =========================================================

@bot.tree.command(
    name="themsp",
    description="Thêm sản phẩm"
)
@app_commands.describe(
    ma="Mã sản phẩm",
    ten="Tên sản phẩm",
    gia="Giá sản phẩm",
    soluong="Số lượng",
    mo_ta="Mô tả"
)
async def add_product(
    interaction: discord.Interaction,
    ma: str,
    ten: str,
    gia: str,
    soluong: int,
    mo_ta: str = "Không có mô tả"
):

    if not isinstance(
        interaction.user,
        discord.Member
    ):
        return

    if not is_staff(
        interaction.user
    ):

        await interaction.response.send_message(
            "❌ Bạn không có quyền.",
            ephemeral=True
        )
        return

    ma = ma.lower().strip()

    if ma in products:

        await interaction.response.send_message(
            "❌ Mã sản phẩm đã tồn tại.",
            ephemeral=True
        )
        return

    if soluong < 0:

        await interaction.response.send_message(
            "❌ Số lượng không hợp lệ.",
            ephemeral=True
        )
        return

    products[ma] = {
        "name": ten,
        "price": gia,
        "stock": soluong,
        "description": mo_ta,
        "available": soluong > 0
    }

    save_json(
        PRODUCTS_FILE,
        products
    )

    await interaction.response.send_message(
        f"✅ Đã thêm sản phẩm **{ten}**.",
        ephemeral=True
    )


# =========================================================
# /SUASP
# =========================================================

@bot.tree.command(
    name="suasp",
    description="Sửa sản phẩm"
)
@app_commands.describe(
    ma="Mã sản phẩm",
    ten="Tên mới",
    gia="Giá mới",
    soluong="Số lượng mới",
    mo_ta="Mô tả mới"
)
async def edit_product(
    interaction: discord.Interaction,
    ma: str,
    ten: str,
    gia: str,
    soluong: int,
    mo_ta: str
):

    if not isinstance(
        interaction.user,
        discord.Member
    ):
        return

    if not is_staff(
        interaction.user
    ):

        await interaction.response.send_message(
            "❌ Bạn không có quyền.",
            ephemeral=True
        )
        return

    ma = ma.lower().strip()

    if ma not in products:

        await interaction.response.send_message(
            "❌ Không tìm thấy sản phẩm.",
            ephemeral=True
        )
        return

    if soluong < 0:

        await interaction.response.send_message(
     
