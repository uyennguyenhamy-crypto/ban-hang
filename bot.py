import os
import json
import re
import discord

from discord.ext import commands
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("TOKEN")

# Kênh đặt bảng SHOP
SHOP_CHANNEL_ID = 1545458090789576723

# Category chứa ticket
TICKET_CATEGORY_ID = 1545458506755473458

# Role nhân viên
STAFF_ROLE_IDS = [
    1537485808229949483,
    1537485814676848690,
    1537485810570498179,
]

PRODUCT_FILE = "products.json"


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True


bot = commands.Bot(
    command_prefix="?",
    intents=intents
)


# ============================================================
# DATABASE
# ============================================================

def load_products():
    if not os.path.exists(PRODUCT_FILE):
        return {}

    try:
        with open(
            PRODUCT_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception as e:
        print(f"[DATABASE] Lỗi đọc file: {e}")

    return {}


def save_products():
    try:
        with open(
            PRODUCT_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                products,
                f,
                ensure_ascii=False,
                indent=4
            )

    except Exception as e:
        print(f"[DATABASE] Lỗi lưu file: {e}")


products = load_products()


# ============================================================
# UTILS
# ============================================================

def money(number):
    return f"{int(number):,}".replace(",", ".") + " VNĐ"


def parse_price(value):
    value = str(value).lower().strip()

    value = value.replace(" ", "")

    if value.endswith("k"):
        try:
            return int(float(value[:-1]) * 1000)
        except:
            return 0

    if value.endswith("m"):
        try:
            return int(float(value[:-1]) * 1000000)
        except:
            return 0

    value = re.sub(r"[^0-9]", "", value)

    if not value:
        return 0

    return int(value)


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


# ============================================================
# SHOP EMBED
# ============================================================

def shop_embed():

    embed = discord.Embed(
        title="🛍️ SHOP ONLINE",
        description=(
            "Chào mừng bạn đến với shop!\n\n"
            "📦 **Bước 1:** Chọn sản phẩm\n"
            "🔢 **Bước 2:** Nhập số lượng\n"
            "💰 **Bước 3:** Kiểm tra tổng tiền\n"
            "✅ **Bước 4:** Xác nhận đơn\n"
            "🎫 **Bước 5:** Ticket được tạo\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💡 Vui lòng kiểm tra sản phẩm "
            "và số lượng trước khi đặt hàng."
        ),
        color=discord.Color.blurple()
    )

    if not products:

        embed.add_field(
            name="📦 Sản phẩm",
            value="Hiện chưa có sản phẩm.",
            inline=False
        )

    else:

        for code, item in list(products.items())[:25]:

            name = item["name"]
            price = item["price"]
            stock = item["stock"]

            if stock > 0:
                status = f"🟢 Còn **{stock}**"
            else:
                status = "🔴 Hết hàng"

            embed.add_field(
                name=f"📦 {name}",
                value=(
                    f"💰 **{money(price)}**\n"
                    f"{status}\n"
                    f"🆔 `{code}`"
                ),
                inline=True
            )

    embed.set_footer(
        text="Shop Bot • Chọn sản phẩm bên dưới"
    )

    return embed


# ============================================================
# PRODUCT SELECT
# ============================================================

class ProductSelect(discord.ui.Select):

    def __init__(self):

        options = []

        for code, item in list(products.items())[:25]:

            if item["stock"] <= 0:
                continue

            options.append(
                discord.SelectOption(
                    label=item["name"][:100],
                    description=(
                        f"{money(item['price'])} • "
                        f"Kho: {item['stock']}"
                    )[:100],
                    value=code,
                    emoji="📦"
                )
            )

        if not options:

            options.append(
                discord.SelectOption(
                    label="Shop chưa có hàng",
                    description="Hiện không có sản phẩm",
                    value="empty",
                    emoji="❌"
                )
            )

        super().__init__(
            placeholder="🛒 Chọn sản phẩm...",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="shop_product_select"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        code = self.values[0]

        if code == "empty":

            await interaction.response.send_message(
                "❌ Hiện shop chưa có sản phẩm.",
                ephemeral=True
            )

            return

        item = products.get(code)

        if not item:

            await interaction.response.send_message(
                "❌ Sản phẩm không tồn tại.",
                ephemeral=True
            )

            return

        if item["stock"] <= 0:

            await interaction.response.send_message(
                "❌ Sản phẩm vừa hết hàng.",
                ephemeral=True
            )

            return

        await interaction.response.send_modal(
            QuantityModal(code)
        )


# ============================================================
# SHOP VIEW
# ============================================================

class ShopView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

        self.add_item(
            ProductSelect()
        )


# ============================================================
# QUANTITY MODAL
# ============================================================

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

    def __init__(self, code):

        super().__init__()

        self.code = code

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        item = products.get(self.code)

        if not item:

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

        if quantity > item["stock"]:

            await interaction.response.send_message(
                f"❌ Kho chỉ còn **{item['stock']}**.",
                ephemeral=True
            )

            return

        total = item["price"] * quantity

        embed = discord.Embed(
            title="📋 XÁC NHẬN ĐƠN HÀNG",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="📦 Sản phẩm",
            value=item["name"],
            inline=False
        )

        embed.add_field(
            name="🔢 Số lượng",
            value=str(quantity),
            inline=True
        )

        embed.add_field(
            name="💰 Đơn giá",
            value=money(item["price"]),
            inline=True
        )

        embed.add_field(
            name="💵 Tổng tiền",
            value=f"**{money(total)}**",
            inline=False
        )

        embed.add_field(
            name="📦 Kho",
            value=str(item["stock"]),
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(
                self.code,
                quantity
            ),
            ephemeral=True
        )


# ============================================================
# CONFIRM VIEW
# ============================================================

class ConfirmView(
    discord.ui.View
):

    def __init__(
        self,
        code,
        quantity
    ):

        super().__init__(
            timeout=300
        )

        self.code = code
        self.quantity = quantity

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

        if guild is None:
            return

        item = products.get(self.code)

        if not item:

            await interaction.response.edit_message(
                content="❌ Sản phẩm không tồn tại.",
                embed=None,
                view=None
            )

            return

        if self.quantity > item["stock"]:

            await interaction.response.edit_message(
                content=(
                    f"❌ Kho chỉ còn "
                    f"**{item['stock']}**."
                ),
                embed=None,
                view=None
            )

            return

        # ----------------------------------------------------
        # CHECK CATEGORY
        # ----------------------------------------------------

        category = guild.get_channel(
            TICKET_CATEGORY_ID
        )

        if not isinstance(
            category,
            discord.CategoryChannel
        ):

            await interaction.response.edit_message(
                content=(
                    "❌ ID Category ticket không đúng.\n\n"
                    f"ID hiện tại:\n"
                    f"`{TICKET_CATEGORY_ID}`\n\n"
                    "Hãy nhập ID của **Category** chứa ticket."
                ),
                embed=None,
                view=None
            )

            return

        # ----------------------------------------------------
        # CHECK OLD TICKET
        # ----------------------------------------------------

        for channel in category.channels:

            if not isinstance(
                channel,
                discord.TextChannel
            ):
                continue

            if str(
                interaction.user.id
            ) in channel.topic if channel.topic else False:

                await interaction.response.edit_message(
                    content=(
                        "❌ Bạn đang có ticket:\n"
                        f"{channel.mention}"
                    ),
                    embed=None,
                    view=None
                )

                return

        # ----------------------------------------------------
        # PERMISSION
        # ----------------------------------------------------

        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
        }

        staff_roles = get_staff_roles(
            guild
        )

        for role in staff_roles:

            overwrites[role] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )
            )

        # ----------------------------------------------------
        # CREATE TICKET
        # ----------------------------------------------------

        username = re.sub(
            r"[^a-zA-Z0-9]",
            "",
            interaction.user.name
        )

        if not username:
            username = "user"

        username = username[:20]

        channel_name = (
            f"ticket-{username}"
        )

        try:

            ticket = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=(
                    f"ticket_user:"
                    f"{interaction.user.id}"
                )
            )

        except discord.Forbidden:

            await interaction.response.edit_message(
                content=(
                    "❌ Bot không có quyền tạo kênh.\n\n"
                    "Cấp cho bot quyền:\n"
                    "• Manage Channels\n"
                    "• View Channels\n"
                    "• Send Messages"
                ),
                embed=None,
                view=None
            )

            return

        except discord.HTTPException as e:

            print(
                f"[TICKET ERROR] {e}"
            )

            await interaction.response.edit_message(
                content="❌ Discord không thể tạo ticket.",
                embed=None,
                view=None
            )

            return

        # ----------------------------------------------------
        # CALCULATE
        # ----------------------------------------------------

        total = (
            item["price"]
            * self.quantity
        )

        # Trừ kho
        item["stock"] -= self.quantity

        save_products()

        # ----------------------------------------------------
        # STAFF MENTION
        # ----------------------------------------------------

        mentions = []

        for role in staff_roles:

            mentions.append(
                role.mention
            )

        staff_text = " ".join(
            mentions
        )

        # ----------------------------------------------------
        # TICKET EMBED
        # ----------------------------------------------------

        embed = discord.Embed(
            title="🎫 ĐƠN HÀNG",
            description=(
                "Đơn hàng đã được tạo thành công.\n"
                "Nhân viên sẽ hỗ trợ bạn tại đây."
            ),
            color=discord.Color.green()
        )

        embed.add_field(
            name="👤 Khách hàng",
            value=interaction.user.mention,
            inline=False
        )

        embed.add_field(
            name="📦 Sản phẩm",
            value=item["name"],
            inline=False
        )

        embed.add_field(
            name="🔢 Số lượng",
            value=str(self.quantity),
            inline=True
        )

        embed.add_field(
            name="💰 Đơn giá",
            value=money(item["price"]),
            inline=True
        )

        embed.add_field(
            name="💵 TỔNG TIỀN",
            value=f"**{money(total)}**",
            inline=False
        )

        embed.add_field(
            name="📦 Kho còn lại",
            value=str(item["stock"]),
            inline=True
        )

        embed.set_footer(
            text="Shop Order System"
        )

        await ticket.send(
            content=(
                f"{interaction.user.mention} "
                f"{staff_text}"
            ),
            embed=embed,
            view=TicketView()
        )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        await interaction.response.edit_message(
            content=(
                "✅ **ĐẶT HÀNG THÀNH CÔNG!**\n\n"
                f"📦 Sản phẩm: **{item['name']}**\n"
                f"🔢 Số lượng: **{self.quantity}**\n"
                f"💵 Tổng: **{money(total)}**\n"
                f"🎫 Ticket: {ticket.mention}"
            ),
            embed=None,
            view=None
        )

        # Cập nhật bảng shop
        await refresh_shop(
            guild
        )

    @discord.ui.button(
        label="Hủy",
        emoji="❌",
        style=discord.ButtonStyle.danger
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.edit_message(
            content="❌ Đã hủy đơn hàng.",
            embed=None,
            view=None
        )


# ============================================================
# TICKET VIEW
# ============================================================

class TicketView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="Đóng ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close"
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
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
                "❌ Chỉ nhân viên mới được đóng ticket.",
                ephemeral=True
            )

            return

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):
            return

        await interaction.response.send_message(
            "🔒 Ticket đã được đóng."
        )

        try:

            await channel.edit(
                name=f"closed-{channel.name}"[:100]
            )

        except discord.HTTPException:
            pass

        # Tắt quyền gửi của mọi member không phải staff
        for member in channel.guild.members:

            if member.bot:
                continue

            if member.id == interaction.user.id:
                continue

            try:

                await channel.set_permissions(
                    member,
                    send_messages=False
                )

            except discord.HTTPException:
                pass


# ============================================================
# REFRESH SHOP
# ============================================================

async def refresh_shop(
    guild
):

    channel = guild.get_channel(
        SHOP_CHANNEL_ID
    )

    if not isinstance(
        channel,
        discord.TextChannel
    ):

        print(
            "[SHOP] Không tìm thấy kênh shop:"
            f" {SHOP_CHANNEL_ID}"
        )

        return

    # Xóa bảng shop cũ của bot
    try:

        async for message in channel.history(
            limit=50
        ):

            if message.author == bot.user:

                if message.embeds:

                    if (
                        message.embeds[0].title
                        ==
