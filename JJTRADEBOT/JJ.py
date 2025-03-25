import discord
import json
import asyncio
import traceback
import re
from discord.ext import commands
import time
import datetime
from discord import app_commands

TOKEN = "MTI5NTQ4ODQ1OTQzNTI4MjQ0Mg.GxNG6_.Xcyw9nQRAS1MvJtqPaDjDo0tcw7pADO3g1NiyE"  # Your Discord account token (self-bot)
GUILD_ID = 1350775755168157739  # Replace with your server ID

bot = commands.Bot(intents=discord.Intents.all(), command_prefix="!")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@bot.tree.command(name="backup", description="Creates a server backup including roles, channels, and user assignments.")
async def backup(interaction: discord.Interaction):
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        await interaction.response.send_message("❌ Guild not found. Check the ID.", ephemeral=True)
        return

    await interaction.response.defer()
    
    # Create initial progress message
    progress_message = await interaction.followup.send(
        "**Server Backup Progress:**\n"
        "⏳ Creating Template\n"
        "➖ Backing up Roles\n"
        "➖ Backing up User Roles\n"
        "➖ Backing up Channels"
    )
    
    await backup_server(guild, progress_message)

async def backup_server(guild, progress_message):
    try:
        # Step 1: Create template
        try:
            existing_templates = await guild.templates()
            for temp in existing_templates:
                await temp.delete()

            template = await guild.create_template(name=f"Backup {guild.name}", description="Full Server Backup")
            template_url = template.url

            with open(r"C:\Users\monfo\OneDrive\Desktop\Bot Clients\JJTRADEBOT\server_backup\backup_template.txt", "w", encoding="utf-8") as file:
                file.write(f"Template URL: {template_url}\n\n")
                
            # Update progress message - Template created
            await progress_message.edit(content=
                "**Server Backup Progress:**\n"
                "✅ Creating Template\n"
                "⏳ Backing up Roles\n"
                "➖ Backing up User Roles\n"
                "➖ Backing up Channels"
            )
        except Exception as e:
            await progress_message.edit(content=
                "**Server Backup Progress:**\n"
                "❌ Creating Template - Error: " + str(e) + "\n"
                "➖ Backing up Roles\n"
                "➖ Backing up User Roles\n"
                "➖ Backing up Channels"
            )
            raise e

        # Step 2: Backup roles
        try:
            # Save roles with their position to maintain hierarchy
            role_data = []
            for role in sorted(guild.roles, key=lambda r: r.position):
                role_data.append({
                    "id": role.id,
                    "name": role.name,
                    "permissions": role.permissions.value,
                    "color": role.color.value,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "position": role.position  # Save position for hierarchy restoration
                })
                
            with open(r"C:\Users\monfo\OneDrive\Desktop\Bot Clients\JJTRADEBOT\server_backup\roles.json", "w", encoding="utf-8") as file:
                json.dump(role_data, file, indent=4)
                
            # Update progress message - Roles backed up
            await progress_message.edit(content=
                "**Server Backup Progress:**\n"
                "✅ Creating Template\n"
                "✅ Backing up Roles\n"
                "⏳ Backing up User Roles\n"
                "➖ Backing up Channels"
            )
        except Exception as e:
            await progress_message.edit(content=
                "**Server Backup Progress:**\n"
                "✅ Creating Template\n"
                "❌ Backing up Roles - Error: " + str(e) + "\n"
                "➖ Backing up User Roles\n"
                "➖ Backing up Channels"
            )
            raise e

        # Step 3: Backup user roles
        try:
            user_roles = {}
            for member in guild.members:
                if member == bot.user:
                    continue
                user_roles[str(member.id)] = [role.name for role in member.roles if role.name != "@everyone"]
                
            with open(r"C:\Users\monfo\OneDrive\Desktop\Bot Clients\JJTRADEBOT\server_backup\user_roles.json", "w", encoding="utf-8") as file:
                json.dump(user_roles, file, indent=4)
                
            # Update progress message - User roles backed up
            await progress_message.edit(content=
                "**Server Backup Progress:**\n"
                "✅ Creating Template\n"
                "✅ Backing up Roles\n"
                "✅ Backing up User Roles\n"
                "⏳ Backing up Channels"
            )
        except Exception as e:
            await progress_message.edit(content=
                "**Server Backup Progress:**\n"
                "✅ Creating Template\n"
                "✅ Backing up Roles\n"
                "❌ Backing up User Roles - Error: " + str(e) + "\n"
                "➖ Backing up Channels"
            )
            raise e

        # Step 4: Backup channels
        try:
            # First backup categories
            categories_data = []
            for category in sorted(guild.categories, key=lambda c: c.position):
                overwrites = {str(target.id): {"allow": overwrite.pair()[0].value, "deny": overwrite.pair()[1].value}
                            for target, overwrite in category.overwrites.items()}
                categories_data.append({
                    "id": category.id,
                    "name": category.name,
                    "position": category.position,
                    "type": "category",
                    "permissions": overwrites
                })
            
            # Then backup channels by category
            channels_data = []
            for category in sorted(guild.categories, key=lambda c: c.position):
                # Add text channels
                for channel in sorted(category.text_channels, key=lambda c: c.position):
                    overwrites = {str(target.id): {"allow": overwrite.pair()[0].value, "deny": overwrite.pair()[1].value}
                                for target, overwrite in channel.overwrites.items()}
                    channels_data.append({
                        "id": channel.id,
                        "name": channel.name,
                        "position": channel.position,
                        "category": category.name,
                        "type": "text",
                        "permissions": overwrites
                    })
                
                # Add voice channels
                for channel in sorted(category.voice_channels, key=lambda c: c.position):
                    overwrites = {str(target.id): {"allow": overwrite.pair()[0].value, "deny": overwrite.pair()[1].value}
                                for target, overwrite in channel.overwrites.items()}
                    channels_data.append({
                        "id": channel.id,
                        "name": channel.name,
                        "position": channel.position,
                        "category": category.name,
                        "type": "voice",
                        "permissions": overwrites
                    })
            
            # Add channels without category
            for channel in sorted([c for c in guild.channels if c.category is None and not isinstance(c, discord.CategoryChannel)], key=lambda c: c.position):
                if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel):
                    overwrites = {str(target.id): {"allow": overwrite.pair()[0].value, "deny": overwrite.pair()[1].value}
                                for target, overwrite in channel.overwrites.items()}
                    channel_type = "text" if isinstance(channel, discord.TextChannel) else "voice"
                    channels_data.append({
                        "id": channel.id,
                        "name": channel.name,
                        "position": channel.position,
                        "category": None,
                        "type": channel_type,
                        "permissions": overwrites
                    })
            
            # Combine categories and channels for the final backup
            combined_data = categories_data + channels_data
                
            with open(r"C:\Users\monfo\OneDrive\Desktop\Bot Clients\JJTRADEBOT\server_backup\channels.json", "w", encoding="utf-8") as file:
                json.dump(combined_data, file, indent=4)
                
            # Update final progress message - All completed
            await progress_message.edit(content=
                "**Server Backup Progress:**\n"
                "✅ Creating Template\n"
                "✅ Backing up Roles\n"
                "✅ Backing up User Roles\n"
                "✅ Backing up Channels\n\n"
                "✅ **Backup Completed Successfully!**"
            )
            with open(r'C:\Users\monfo\OneDrive\Desktop\Bot Clients\JJTRADEBOT\server_backup\timenow.txt', 'w', encoding='utf-8') as f:
                #clear everything in the file
                f.truncate(0)
                #write the current time
                f.write(str(round(datetime.datetime.timestamp(datetime.datetime.now()))))

        except Exception as e:
            await progress_message.edit(content=
                "**Server Backup Progress:**\n"
                "✅ Creating Template\n"
                "✅ Backing up Roles\n"
                "✅ Backing up User Roles\n"
                "❌ Backing up Channels - Error: " + str(e) + "\n\n"
                "❌ **Backup Failed!**"
            )
            raise e

    except discord.Forbidden:
        await progress_message.edit(content=
            "**Server Backup Progress:**\n"
            "❌ **Backup Failed: Bot lacks permissions to create a server template.**"
        )
    except Exception as e:
        await progress_message.edit(content=
            "**Server Backup Progress:**\n"
            f"❌ **Backup Failed: {str(e)}**"
        )

# create a button view
class ConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.value = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.send_message("Starting restoration process...", ephemeral=True)
        self.stop()
        
    @discord.ui.button(label="No", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.send_message("Restoration cancelled.", ephemeral=True)
        self.stop()

@bot.tree.command(name="restore", description="Restores server roles, user assignments, and channels from backup.")
async def restore(interaction: discord.Interaction):
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        await interaction.response.send_message("❌ Failed to find the server.", ephemeral=True)
        return
    
    with open(r'C:\Users\monfo\OneDrive\Desktop\Bot Clients\JJTRADEBOT\server_backup\timenow.txt', 'r', encoding='utf-8') as f:
        last_backup = f.read()
    
    # Create the confirmation view
    view = ConfirmationView()
    
    # Send message with confirmation buttons
    await interaction.response.send_message(
        f"⚠️ **IMPORTANT**: Are you sure you want to restore from the backup taken on <t:{last_backup}>?", 
        view=view,
        ephemeral=True
    )
    
    # Wait for the user to interact with the view
    timeout = await view.wait()
    
    # If the view times out
    if timeout:
        await interaction.followup.send("Restoration cancelled - you didn't respond in time.", ephemeral=True)
        return
    
    # Check if the user confirmed
    if not view.value:
        return
    
    # Create initial progress message
    progress_message = await interaction.followup.send(
        "**Server Restore Progress:**\n"
        "⏳ Restoring Roles\n"
        "➖ Restoring User Roles\n"
        "➖ Restoring Channels"
    )
    
    try:
        # Step 1: Restore roles
        role_map = await restore_roles(guild)
        
        # Update progress message - Roles restored
        await progress_message.edit(content=
            "**Server Restore Progress:**\n"
            "✅ Restoring Roles\n"
            "⏳ Restoring User Roles\n"
            "➖ Restoring Channels"
        )
        
        # Step 2: Restore user roles
        await restore_user_roles(guild, role_map)
        
        # Update progress message - User roles restored
        await progress_message.edit(content=
            "**Server Restore Progress:**\n"
            "✅ Restoring Roles\n"
            "✅ Restoring User Roles\n"
            "⏳ Restoring Channels\n\n*⚠️ Note: Restoring channels may take **up to 10 minutes** to complete for large servers*"
        )
        
        # Step 3: Restore channels
        await restore_channels(guild, role_map)
        
        # Update final progress message - All completed
        await progress_message.edit(content=
            "**Server Restore Progress:**\n"
            "✅ Restoring Roles\n"
            "✅ Restoring User Roles\n"
            "✅ Restoring Channels\n\n"
            "✅ **Server Restored Successfully!**"
        )
    except Exception as e:
        # If any step fails, show the error in the progress message
        await progress_message.edit(content=
            "**Server Restore Progress:**\n"
            f"❌ **Restore Failed: {str(e)}**"
        )

async def restore_roles(guild):
    try:
        with open(r"C:\Users\monfo\OneDrive\Desktop\Bot Clients\JJTRADEBOT\server_backup\roles.json", "r", encoding="utf-8") as file:
            roles_data = json.load(file)

        # Sort roles by position for proper hierarchy restoration
        roles_data.sort(key=lambda r: r["position"])
        
        role_map = {role.name: role for role in guild.roles}
        created_roles = []

        # First pass: Create all missing roles
        for role_info in roles_data:
            if role_info["name"] not in role_map:
                role = await guild.create_role(
                    name=role_info["name"],
                    permissions=discord.Permissions(role_info["permissions"]),
                    color=discord.Color(role_info["color"]),
                    hoist=role_info["hoist"],
                    mentionable=role_info["mentionable"]
                )
                role_map[role_info["name"]] = role
                created_roles.append((role, role_info["position"]))

        # Second pass: Adjust positions of all created roles
        # Sort in reverse order so we move the highest roles first
        for role, position in sorted(created_roles, key=lambda x: x[1], reverse=True):
            try:
                # Adjust role position if needed
                if role.position != position and role.name != "@everyone":
                    await role.edit(position=position)
                    # Add a small delay to prevent rate limiting
                    await asyncio.sleep(0.5)
            except discord.HTTPException:
                # Skip position adjustment if we hit an error (like moving above the bot's highest role)
                continue

        return role_map
    except Exception as e:
        print(f"Error restoring roles: {e}")
        raise Exception(f"Failed to restore roles: {e}")

async def restore_user_roles(guild, role_map):
    try:
        with open(r"C:\Users\monfo\OneDrive\Desktop\Bot Clients\JJTRADEBOT\server_backup\user_roles.json", "r", encoding="utf-8") as file:
            user_roles = json.load(file)

        for user_id, roles in user_roles.items():
            member = guild.get_member(int(user_id))
            if member:
                new_roles = [role_map[role_name] for role_name in roles if role_name in role_map]
                if new_roles:
                    await member.add_roles(*new_roles)
                    # Add a small delay to prevent rate limiting
                    await asyncio.sleep(0.5)
    except Exception as e:
        print(f"Error restoring user roles: {e}")
        raise Exception(f"Failed to restore user roles: {e}")

async def restore_channels(guild, role_map):
    try:
        print(f"[RESTORE] Starting channel restoration process for guild: {guild.name}")
        with open(r"C:\Users\monfo\OneDrive\Desktop\Bot Clients\JJTRADEBOT\server_backup\channels.json", "r", encoding="utf-8") as file:
            channels_data = json.load(file)
        print(f"[RESTORE] Loaded {len(channels_data)} channels from backup")

        # Create dictionaries of existing channels and categories for quick lookup
        existing_categories = {category.name: category for category in guild.categories}
        existing_text_channels = {channel.name: channel for channel in guild.text_channels}
        existing_voice_channels = {channel.name: channel for channel in guild.voice_channels}
        print(f"[RESTORE] Found {len(existing_categories)} existing categories, {len(existing_text_channels)} text channels, {len(existing_voice_channels)} voice channels")
        
        # Separate categories and regular channels
        category_channels = [c for c in channels_data if c["type"] == "category"]
        regular_channels = [c for c in channels_data if c["type"] != "category"]
        print(f"[RESTORE] Need to process {len(category_channels)} categories and {len(regular_channels)} regular channels")
        
        # Sort categories by position
        category_channels.sort(key=lambda x: x["position"])
        
        # Process categories first
        print("[RESTORE] === PROCESSING CATEGORIES ===")
        categories_created = 0
        categories_updated = 0
        categories_unchanged = 0
        
        for channel_info in category_channels:
            print(f"[RESTORE] Processing category: {channel_info['name']}")
            overwrites = await get_permission_overwrites(guild, channel_info["permissions"])
            
            if channel_info["name"] in existing_categories:
                # Check if permissions need updating
                category = existing_categories[channel_info["name"]]
                current_overwrites = category.overwrites
                
                # Only update if permissions are different
                if not are_overwrites_equal(current_overwrites, overwrites):
                    print(f"[RESTORE] Updating permissions for category: {channel_info['name']}")
                    await category.edit(overwrites=overwrites)
                    categories_updated += 1
                    await asyncio.sleep(1)
                else:
                    print(f"[RESTORE] No changes needed for category: {channel_info['name']}")
                    categories_unchanged += 1
            else:
                # Create missing category
                print(f"[RESTORE] Creating missing category: {channel_info['name']}")
                category = await guild.create_category(
                    name=channel_info["name"],
                    overwrites=overwrites
                )
                existing_categories[channel_info["name"]] = category
                categories_created += 1
                await asyncio.sleep(1)
        
        print(f"[RESTORE] Categories summary: {categories_created} created, {categories_updated} updated, {categories_unchanged} unchanged")
        
        # Sort regular channels by category and position
        regular_channels.sort(key=lambda x: (x["category"] if x["category"] else "", x["position"]))
        
        # Process regular channels
        print("[RESTORE] === PROCESSING REGULAR CHANNELS ===")
        channels_created = 0
        channels_updated = 0
        channels_unchanged = 0
        channels_errors = 0
        
        for channel_info in regular_channels:
            print(f"[RESTORE] Processing channel: {channel_info['name']} (Type: {channel_info['type']}, Category: {channel_info['category']})")
            category = existing_categories.get(channel_info["category"])
            if channel_info["category"] and not category:
                print(f"[RESTORE] Warning: Category '{channel_info['category']}' not found for channel {channel_info['name']}")
                
            overwrites = await get_permission_overwrites(guild, channel_info["permissions"])
            
            # Check if channel exists
            if channel_info["type"] == "text":
                existing_channel = existing_text_channels.get(channel_info["name"])
            elif channel_info["type"] == "voice":
                existing_channel = existing_voice_channels.get(channel_info["name"])
            else:
                existing_channel = None
            
            if existing_channel:
                # Check if channel needs updating (category or permissions)
                needs_update = False
                update_reasons = []
                
                if existing_channel.category != category:
                    needs_update = True
                    if category:
                        update_reasons.append(f"change category to '{category.name}'")
                    else:
                        update_reasons.append("remove from category")
                
                if not are_overwrites_equal(existing_channel.overwrites, overwrites):
                    needs_update = True
                    update_reasons.append("update permissions")
                
                if needs_update:
                    try:
                        print(f"[RESTORE] Updating channel '{existing_channel.name}' to {', '.join(update_reasons)}")
                        await existing_channel.edit(
                            category=category,
                            overwrites=overwrites
                        )
                        channels_updated += 1
                        await asyncio.sleep(1)
                    except Exception as e:
                        print(f"[RESTORE] Error updating channel {existing_channel.name}: {e}")
                        channels_errors += 1
                else:
                    print(f"[RESTORE] No changes needed for channel: {existing_channel.name}")
                    channels_unchanged += 1
            else:
                # Create missing channel
                try:
                    print(f"[RESTORE] Creating missing channel: {channel_info['name']}")
                    if channel_info["type"] == "text":
                        channel = await guild.create_text_channel(
                            name=channel_info["name"],
                            category=category,
                            overwrites=overwrites
                        )
                    elif channel_info["type"] == "voice":
                        channel = await guild.create_voice_channel(
                            name=channel_info["name"],
                            category=category,
                            overwrites=overwrites
                        )
                    channels_created += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"[RESTORE] Error creating channel {channel_info['name']}: {e}")
                    channels_errors += 1
        
        print(f"[RESTORE] Regular channels summary: {channels_created} created, {channels_updated} updated, {channels_unchanged} unchanged, {channels_errors} errors")
        
        # Fix channel positions for channels that need it
        print("[RESTORE] === FIXING CHANNEL POSITIONS ===")
        channels_by_category = {}
        for channel_info in regular_channels:
            category_name = channel_info["category"] if channel_info["category"] else None
            if category_name not in channels_by_category:
                channels_by_category[category_name] = []
            channels_by_category[category_name].append(channel_info)
        
        positions_updated = 0
        positions_unchanged = 0
        positions_errors = 0
        
        for category_name, channels in channels_by_category.items():
            # Sort channels by intended position
            channels.sort(key=lambda x: x["position"])
            
            print(f"[RESTORE] Checking positions for {len(channels)} channels in category: {category_name}")
            
            # Get the Discord category object
            category = existing_categories.get(category_name)
            
            if category:
                # Get current channel positions
                current_positions = {}
                for channel in category.channels:
                    current_positions[channel.name] = channel.position
                
                # Create a map of channel name to intended position
                intended_positions = {}
                for i, channel_info in enumerate(channels):
                    intended_positions[channel_info["name"]] = i
                
                # Get channels that need position updates
                channels_to_update = []
                for channel in category.channels:
                    if channel.name in intended_positions:
                        if current_positions[channel.name] != intended_positions[channel.name]:
                            channels_to_update.append((channel, intended_positions[channel.name]))
                            print(f"[RESTORE] Channel '{channel.name}' needs position change: {current_positions[channel.name]} → {intended_positions[channel.name]}")
                        else:
                            print(f"[RESTORE] Channel '{channel.name}' already in correct position: {current_positions[channel.name]}")
                
                # Update positions only if needed
                if channels_to_update:
                    print(f"[RESTORE] Updating positions for {len(channels_to_update)} channels in category '{category_name}'")
                    for channel, position in sorted(channels_to_update, key=lambda x: x[1]):
                        try:
                            print(f"[RESTORE] Setting position for channel '{channel.name}' to {position}")
                            await channel.edit(position=position)
                            positions_updated += 1
                            await asyncio.sleep(1)
                        except Exception as e:
                            print(f"[RESTORE] Error setting position for {channel.name}: {e}")
                            positions_errors += 1
                else:
                    print(f"[RESTORE] All channels in category '{category_name}' already in correct positions")
                    positions_unchanged += len(category.channels)
        
        print(f"[RESTORE] Channel positions summary: {positions_updated} updated, {positions_unchanged} unchanged, {positions_errors} errors")
        
        # Fix category positions only if needed
        print("[RESTORE] === FIXING CATEGORY POSITIONS ===")
        current_category_positions = {category.name: category.position for category in guild.categories}
        
        categories_to_update = []
        for i, category_info in enumerate(category_channels):
            category = existing_categories.get(category_info["name"])
            if category and current_category_positions[category.name] != i:
                categories_to_update.append((category, i))
                print(f"[RESTORE] Category '{category.name}' needs position change: {current_category_positions[category.name]} → {i}")
            elif category:
                print(f"[RESTORE] Category '{category.name}' already in correct position: {current_category_positions[category.name]}")
        
        cat_positions_updated = 0
        cat_positions_errors = 0
        
        if categories_to_update:
            print(f"[RESTORE] Updating positions for {len(categories_to_update)} categories")
            for category, position in sorted(categories_to_update, key=lambda x: x[1], reverse=True):
                try:
                    print(f"[RESTORE] Setting position for category '{category.name}' to {position}")
                    await category.edit(position=position)
                    cat_positions_updated += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"[RESTORE] Error setting position for category {category.name}: {e}")
                    cat_positions_errors += 1
        else:
            print("[RESTORE] All categories already in correct positions")
            
        print(f"[RESTORE] Category positions summary: {cat_positions_updated} updated, {len(category_channels) - cat_positions_updated - cat_positions_errors} unchanged, {cat_positions_errors} errors")
        print("[RESTORE] === CHANNEL RESTORATION COMPLETED ===")
                    
    except Exception as e:
        print(f"[RESTORE] CRITICAL ERROR: {e}")
        print(f"[RESTORE] Traceback: {traceback.format_exc()}")
        raise Exception(f"Failed to restore channels: {e}")

def are_overwrites_equal(overwrites1, overwrites2):
    """Helper function to compare permission overwrites"""
    if len(overwrites1) != len(overwrites2):
        return False
    
    for target, overwrite in overwrites1.items():
        if target not in overwrites2:
            return False
        
        other_overwrite = overwrites2[target]
        if overwrite.pair() != other_overwrite.pair():
            return False
    
    return True

async def get_permission_overwrites(guild, permissions_data):
    """Helper function to convert permissions data to Discord overwrites"""
    overwrites = {}
    
    for target_id, perms in permissions_data.items():
        # Try to get the role or member
        target = guild.get_role(int(target_id)) or guild.get_member(int(target_id))
        
        if target:
            overwrites[target] = discord.PermissionOverwrite.from_pair(
                discord.Permissions(perms["allow"]),
                discord.Permissions(perms["deny"])
            )
    
    return overwrites

@bot.tree.command(name="embed", description="Send a custom embedded message to the channel")
@app_commands.describe(
    title="Title of the embed",
    description="Main content of the embed",
    color="Color of the embed (hex code like #FF5733)",
    image_url="Optional URL for an embed image",
    thumbnail_url="Optional URL for an embed thumbnail"
)
async def send_embed(interaction: discord.Interaction, title: str, description: str, color: str = "#5865F2", 
                    image_url: str = None, thumbnail_url: str = None):
    try:
        # Convert hex to discord color
        color_int = int(color.replace('#', ''), 16)
        embed = discord.Embed(title=title, description=description, color=color_int)
        
        # Add image if provided
        if image_url:
            embed.set_image(url=image_url)
            
        # Add thumbnail if provided
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
            
        # Add footer with author name
        embed.set_footer(text=f"Sent by {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        # Add timestamp
        embed.timestamp = datetime.datetime.now()
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        error_embed = discord.Embed(
            title="⚠️ Error",
            description=f"```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(
    member="The member to kick",
    reason="Reason for kicking the member"
)
@app_commands.checks.has_permissions(kick_members=True)
async def kick_member(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        error_embed = discord.Embed(
            title="⛔ Permission Error",
            description="You cannot kick someone with a role higher than or equal to yours!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return
        
    try:
        await member.kick(reason=f"{reason} - By {interaction.user}")
        
        success_embed = discord.Embed(
            title="👢 Member Kicked",
            description=f"{member.mention} has been kicked from the server.",
            color=discord.Color.orange()
        )
        success_embed.add_field(name="Reason", value=reason, inline=False)
        success_embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        success_embed.add_field(name="User ID", value=member.id, inline=True)
        success_embed.set_thumbnail(url=member.display_avatar.url)
        success_embed.timestamp = datetime.datetime.now()
        
        await interaction.response.send_message(embed=success_embed)
    except Exception as e:
        error_embed = discord.Embed(
            title="⚠️ Error",
            description=f"Failed to kick member: ```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(
    member="The member to ban",
    reason="Reason for banning the member",
    delete_days="Number of days of messages to delete (0-7)"
)
@app_commands.checks.has_permissions(ban_members=True)
async def ban_member(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_days: int = 1):
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        error_embed = discord.Embed(
            title="⛔ Permission Error",
            description="You cannot ban someone with a role higher than or equal to yours!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return
        
    if delete_days < 0 or delete_days > 7:
        error_embed = discord.Embed(
            title="⚠️ Invalid Input",
            description="Delete days must be between 0 and 7!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return
        
    try:
        await member.ban(reason=f"{reason} - By {interaction.user}", delete_message_days=delete_days)
        
        ban_embed = discord.Embed(
            title="🔨 Member Banned",
            description=f"{member.mention} has been banned from the server.",
            color=discord.Color.dark_red()
        )
        ban_embed.add_field(name="Reason", value=reason, inline=False)
        ban_embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        ban_embed.add_field(name="User ID", value=member.id, inline=True)
        ban_embed.add_field(name="Messages Deleted", value=f"{delete_days} days", inline=True)
        ban_embed.set_thumbnail(url=member.display_avatar.url)
        ban_embed.timestamp = datetime.datetime.now()
        
        await interaction.response.send_message(embed=ban_embed)
    except Exception as e:
        error_embed = discord.Embed(
            title="⚠️ Error",
            description=f"Failed to ban member: ```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

@bot.tree.command(name="timeout", description="Timeout (mute) a member")
@app_commands.describe(
    member="The member to timeout",
    duration="Timeout duration (e.g. 1h, 30m, 12h)",
    reason="Reason for the timeout"
)
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout_member(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason provided"):
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        error_embed = discord.Embed(
            title="⛔ Permission Error",
            description="You cannot timeout someone with a role higher than or equal to yours!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return
    
    # Parse duration string (e.g. 1h, 30m, 12h)
    time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    time_regex = re.compile(r"^(\d+)([smhd])$")
    match = time_regex.match(duration.lower())
    
    if not match:
        error_embed = discord.Embed(
            title="⚠️ Invalid Format",
            description="Duration format should be a number followed by s, m, h, or d (e.g. 30m, 1h, 1d)",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return
    
    value, unit = match.groups()
    seconds = int(value) * time_units[unit]
    
    if seconds > 86400 * 28:  # Discord's max timeout is 28 days
        error_embed = discord.Embed(
            title="⚠️ Invalid Duration",
            description="Timeout duration cannot exceed 28 days!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)
        return
    
    try:
        # Calculate until time for the human-readable format
        until_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
        human_readable_time = f"{value}{unit}"
        
        # Apply timeout - corrected line
        await member.timeout(until_time, reason=f"{reason} - By {interaction.user}")
        
        timeout_embed = discord.Embed(
            title="🔇 Member Timed Out",
            description=f"{member.mention} has been timed out.",
            color=discord.Color.gold()
        )
        timeout_embed.add_field(name="Duration", value=human_readable_time, inline=True)
        timeout_embed.add_field(name="Expires", value=f"<t:{int(until_time.timestamp())}:R>", inline=True)
        timeout_embed.add_field(name="Reason", value=reason, inline=False)
        timeout_embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        timeout_embed.set_thumbnail(url=member.display_avatar.url)
        timeout_embed.timestamp = datetime.datetime.now()
        
        await interaction.response.send_message(embed=timeout_embed)
    except Exception as e:
        error_embed = discord.Embed(
            title="⚠️ Error",
            description=f"Failed to timeout member: ```{str(e)}```",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

# Set up logging channel ID
LOG_CHANNEL_ID = 1350851647416438906  # Replace with your log channel ID

@bot.event
async def on_member_join(member):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        join_embed = discord.Embed(
            title="👋 Member Joined",
            description=f"{member.mention} has joined the server.",
            color=discord.Color.green()
        )
        join_embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        join_embed.add_field(name="User ID", value=member.id, inline=True)
        join_embed.set_thumbnail(url=member.display_avatar.url)
        join_embed.set_footer(text=f"Server member count: {member.guild.member_count}")
        join_embed.timestamp = datetime.datetime.now()
        
        await log_channel.send(embed=join_embed)

@bot.event
async def on_member_remove(member):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        leave_embed = discord.Embed(
            title="👋 Member Left",
            description=f"{member.mention} has left the server.",
            color=discord.Color.red()
        )
        leave_embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
        leave_embed.add_field(name="User ID", value=member.id, inline=True)
        leave_embed.add_field(name="Roles", value=", ".join([role.mention for role in member.roles[1:]]) or "None", inline=False)
        leave_embed.set_thumbnail(url=member.display_avatar.url)
        leave_embed.set_footer(text=f"Server member count: {member.guild.member_count}")
        leave_embed.timestamp = datetime.datetime.now()
        
        await log_channel.send(embed=leave_embed)

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        delete_embed = discord.Embed(
            title="🗑️ Message Deleted",
            description=f"Message by {message.author.mention} was deleted in {message.channel.mention}",
            color=discord.Color.orange()
        )
        
        if message.content:
            if len(message.content) > 1024:
                delete_embed.add_field(name="Content", value=f"```{message.content[:1021]}...```", inline=False)
            else:
                delete_embed.add_field(name="Content", value=f"```{message.content}```", inline=False)
        
        if message.attachments:
            attachment_list = "\n".join([a.url for a in message.attachments])
            if len(attachment_list) > 1024:
                delete_embed.add_field(name="Attachments", value=attachment_list[:1021] + "...", inline=False)
            else:
                delete_embed.add_field(name="Attachments", value=attachment_list, inline=False)
        
        delete_embed.add_field(name="User ID", value=message.author.id, inline=True)
        delete_embed.add_field(name="Message ID", value=message.id, inline=True)
        delete_embed.set_thumbnail(url=message.author.display_avatar.url)
        delete_embed.timestamp = datetime.datetime.now()
        
        await log_channel.send(embed=delete_embed)

bot.run(TOKEN)