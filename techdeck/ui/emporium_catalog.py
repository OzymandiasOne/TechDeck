"""
The Emporium merchandise catalog — pure data, no Qt.

Every item carries a "category" so the store can group merchandise. New items
just append here with a category and flow into the right tab automatically.
Categories with no items render a "COMING SOON" plate (see EmporiumPage.CATEGORIES).

Imported by the Emporium/My Stuff pages, garden_scene (furniture ownership),
and the placement dev tools (tools/furniture_placer.py etc.).
"""

CATALOG = [
    # Rebuilt into three layers like the rest, but KEEPS its item id so
    # existing purchases and equipped saves survive.
    {"id": "spinner_beyblade", "name": "Beyblade", "category": "toys",
     "sprite": "beyblade/classic", "cost": 60, "kind": "beyblade"},
    {"id": "spinner_shuriken", "name": "Shuriken", "category": "toys",
     "sprite": "spinner_shuriken.tdart", "cost": 100, "kind": "spinner"},

    # Beyblades ship as THREE parts each (top / bottom / centre). Buying one
    # unlocks its three parts for mixing -- a player who owns two can wear one's
    # top over the other's bottom. `kind: beyblade` tells the store to compose a
    # preview from the parts rather than look for a single sprite file.
    {"id": "bey_silver_fang", "name": "Silver Fang", "category": "toys",
     "sprite": "beyblade/silver_fang", "cost": 120, "kind": "beyblade"},
    {"id": "bey_tidewing", "name": "Tidewing", "category": "toys",
     "sprite": "beyblade/tidewing", "cost": 140, "kind": "beyblade"},
    {"id": "bey_ironclad", "name": "Ironclad", "category": "toys",
     "sprite": "beyblade/ironclad", "cost": 150, "kind": "beyblade"},
    {"id": "bey_forgeheart", "name": "Forgeheart", "category": "toys",
     "sprite": "beyblade/forgeheart", "cost": 160, "kind": "beyblade"},
    {"id": "bey_verdanox", "name": "Verdanox", "category": "toys",
     "sprite": "beyblade/verdanox", "cost": 170, "kind": "beyblade"},
    {"id": "bey_nightspur", "name": "Nightspur", "category": "toys",
     "sprite": "beyblade/nightspur", "cost": 190, "kind": "beyblade"},
    {"id": "game_asa_the_video_game", "name": "ASA: The Video Game", "category": "toys",
     "sprite": "cartridge_steeltube.tdart", "cost": 250, "kind": "game"},
    # A GADGET: it doesn't get equipped, it gets CONFIGURED. Owning it unlocks
    # the kill-cam file/folder picker plus the per-app switches in My Stuff and
    # in Settings -> Apps (techdeck/core/sentry_mode.py).
    {"id": "toy_sentry_drone", "name": "Sentry Drone", "category": "toys",
     "sprite": "sentry_drone.tdart", "cost": 200, "kind": "gadget"},

    # --- Friends: companions for My House (kind "friends"; PNG sprites). ---
    {"id": "friend_buddy", "name": "Buddy", "category": "friends",
     "sprite": "sPet_Buddy_4.png", "cost": 120, "kind": "friends"},

    # --- Decorations: furniture for My House (kind "furniture"; PNG sprites). ---
    # Bought items are recorded as owned; placement into rooms is the next pass.
    {"id": "deco_rug", "name": "Rug", "category": "decorations",
     "sprite": "sPet_ItemRug_0.png", "cost": 25, "kind": "furniture"},
    {"id": "deco_plant", "name": "Plant", "category": "decorations",
     "sprite": "sPet_ItemPlant_0.png", "cost": 25, "kind": "furniture"},
    {"id": "deco_lamp", "name": "Lamp", "category": "decorations",
     "sprite": "sPet_ItemLamp_0.png", "cost": 25, "kind": "furniture"},
    {"id": "deco_toilet", "name": "Toilet", "category": "decorations",
     "sprite": "sPet_ItemToilet_0.png", "cost": 30, "kind": "furniture"},
    {"id": "deco_mirror", "name": "Mirror", "category": "decorations",
     "sprite": "sPet_ItemMirror_0.png", "cost": 30, "kind": "furniture"},
    {"id": "deco_hatrack", "name": "Hat Rack", "category": "decorations",
     "sprite": "sPet_ItemHatrack_0.png", "cost": 30, "kind": "furniture"},
    {"id": "deco_phone", "name": "Telephone", "category": "decorations",
     "sprite": "sPet_ItemPhone_0.png", "cost": 35, "kind": "furniture"},
    {"id": "deco_painting", "name": "Painting", "category": "decorations",
     "sprite": "sPet_ItemPainting_0.png", "cost": 35, "kind": "furniture"},
    {"id": "deco_couch", "name": "Couch", "category": "decorations",
     "sprite": "sPet_ItemCouch_0.png", "cost": 40, "kind": "furniture"},
    {"id": "deco_books", "name": "Bookshelf", "category": "decorations",
     "sprite": "sPet_ItemBooks_0.png", "cost": 40, "kind": "furniture"},
    {"id": "deco_desk", "name": "Desk", "category": "decorations",
     "sprite": "sPet_ItemDesk_0.png", "cost": 45, "kind": "furniture"},
    {"id": "deco_tub", "name": "Bathtub", "category": "decorations",
     "sprite": "sPet_ItemTub_0.png", "cost": 45, "kind": "furniture"},
    {"id": "deco_bed", "name": "Bed", "category": "decorations",
     "sprite": "sPet_ItemBed_0.png", "cost": 50, "kind": "furniture"},
    {"id": "deco_guitar", "name": "Guitar", "category": "decorations",
     "sprite": "sPet_ItemGuitar_0.png", "cost": 50, "kind": "furniture"},
    {"id": "deco_fridge", "name": "Fridge", "category": "decorations",
     "sprite": "sPet_ItemFridge_0.png", "cost": 55, "kind": "furniture"},
    {"id": "deco_stove", "name": "Stove", "category": "decorations",
     "sprite": "sPet_ItemStove_0.png", "cost": 55, "kind": "furniture"},
    {"id": "deco_tv", "name": "TV", "category": "decorations",
     "sprite": "sPet_ItemTV_0.png", "cost": 60, "kind": "furniture"},
    {"id": "deco_telescope", "name": "Telescope", "category": "decorations",
     "sprite": "sPet_ItemTelescope_0.png", "cost": 70, "kind": "furniture"},
    {"id": "deco_hottub", "name": "Hot Tub", "category": "decorations",
     "sprite": "sPet_ItemHotTub_0.png", "cost": 80, "kind": "furniture"},
    {"id": "deco_trophy", "name": "Trophy", "category": "decorations",
     "sprite": "sPet_ItemTrophy_0.png", "cost": 100, "kind": "furniture"},
    # --- more furniture (indoor) ---
    {"id": "deco_computer", "name": "Computer", "category": "decorations",
     "sprite": "sPet_ItemLx_0.png", "cost": 70, "kind": "furniture"},
    {"id": "deco_blender", "name": "Blender", "category": "decorations",
     "sprite": "sPet_ItemBlender_0.png", "cost": 40, "kind": "furniture"},
    {"id": "deco_easel", "name": "Easel", "category": "decorations",
     "sprite": "sPet_ItemCanvas_0.png", "cost": 45, "kind": "furniture"},
    {"id": "deco_calendar", "name": "Calendar", "category": "decorations",
     "sprite": "sPet_ItemCalendar_0.png", "cost": 20, "kind": "furniture"},
    {"id": "deco_chest", "name": "Chest", "category": "decorations",
     "sprite": "sPet_ItemTrunk_0.png", "cost": 50, "kind": "furniture"},
    {"id": "deco_boxes", "name": "Boxes", "category": "decorations",
     "sprite": "sPet_ItemBoxes_0.png", "cost": 20, "kind": "furniture"},
    {"id": "deco_cobweb", "name": "Cobweb", "category": "decorations",
     "sprite": "sPet_ItemSpider_0.png", "cost": 15, "kind": "furniture"},
    {"id": "deco_trapdoor", "name": "Trap Door", "category": "decorations",
     "sprite": "sPet_ItemTrapDoor_0.png", "cost": 30, "kind": "furniture"},
    # --- more furniture (yard) ---
    {"id": "deco_picnic", "name": "Picnic Blanket", "category": "decorations",
     "sprite": "sPet_ItemPicnicBlanket_0.png", "cost": 35, "kind": "furniture"},
    {"id": "deco_watercan", "name": "Watering Can", "category": "decorations",
     "sprite": "sPet_ItemWaterCan_0.png", "cost": 25, "kind": "furniture"},
    {"id": "deco_bike", "name": "Bike", "category": "decorations",
     "sprite": "sPet_ItemBike_0.png", "cost": 40, "kind": "furniture"},
    {"id": "deco_jumprope", "name": "Jump Rope", "category": "decorations",
     "sprite": "sPet_ItemJumpRope_0.png", "cost": 20, "kind": "furniture"},
    {"id": "deco_gardenplot", "name": "Garden Plot", "category": "decorations",
     "sprite": "sPet_ItemDirt_0.png", "cost": 30, "kind": "furniture"},
    {"id": "deco_cattails", "name": "Cattails", "category": "decorations",
     "sprite": "sPet_ItemCattails_0.png", "cost": 25, "kind": "furniture"},
    {"id": "deco_flower", "name": "Flower", "category": "decorations",
     "sprite": "sPet_ItemFlower_0.png", "cost": 20, "kind": "furniture"},
    {"id": "deco_lilypad", "name": "Lily Pad", "category": "decorations",
     "sprite": "sPet_ItemLily_0.png", "cost": 25, "kind": "furniture"},
    {"id": "deco_satellite", "name": "Satellite", "category": "decorations",
     "sprite": "sPet_ItemSatellite_0.png", "cost": 80, "kind": "furniture"},
    {"id": "deco_bird", "name": "Bird", "category": "decorations",
     "sprite": "sPet_ItemBird_0.png", "cost": 30, "kind": "furniture"},
    {"id": "deco_anthill", "name": "Anthill", "category": "decorations",
     "sprite": "sPet_ItemAnts_0.png", "cost": 15, "kind": "furniture"},
    {"id": "deco_butterfly", "name": "Butterfly", "category": "decorations",
     "sprite": "sPet_ItemButterfly_0.png", "cost": 25, "kind": "furniture"},
    {"id": "deco_sapling", "name": "Tree Sapling", "category": "decorations",
     "sprite": "sPet_Tree_5.png", "cost": 30, "kind": "tree"},
    # Buying the Sun also unlocks the Moon, which is hidden from the store + My
    # Stuff so it's a surprise the player discovers on a night background.
    {"id": "deco_sun", "name": "Sun", "category": "decorations",
     "sprite": "sPet_ItemSun_0.png", "cost": 40, "kind": "furniture",
     "bundle": ["deco_moon"]},
    {"id": "deco_moon", "name": "Moon", "category": "decorations",
     "sprite": "sPet_ItemSunMoon_0.png", "cost": 40, "kind": "furniture",
     "hidden": True},
    # Owl + Monkey live in the tree — only sold once it's fully grown.
    {"id": "deco_owl", "name": "Owl", "category": "decorations",
     "sprite": "sPet_ItemOwl_0.png", "cost": 80, "kind": "furniture",
     "requires": "tree_full"},
    {"id": "deco_monkey", "name": "Monkey", "category": "decorations",
     "sprite": "sPet_ItemMonkey_0.png", "cost": 100, "kind": "furniture",
     "requires": "tree_full"},

    # --- Decorations: backgrounds (equippable My House wallpaper). sLibraryBG_4
    # is the free default; these are the alternates. Equip by buying / re-clicking.
    {"id": "bg_blue_stripes", "name": "Blue Stripes", "category": "decorations",
     "sprite": "sLibraryBG_5.png", "cost": 60, "kind": "background"},
    {"id": "bg_gold_stripes", "name": "Gold Stripes", "category": "decorations",
     "sprite": "sLibraryBG_6.png", "cost": 60, "kind": "background"},
    {"id": "bg_starry_night", "name": "Starry Night", "category": "decorations",
     "sprite": "sLibraryBG_7.png", "cost": 90, "kind": "background"},
    {"id": "bg_fireworks", "name": "Fireworks", "category": "decorations",
     "sprite": "sLibraryBG_8.png", "cost": 120, "kind": "background"},
    {"id": "bg_bubblegum", "name": "Bubblegum", "category": "decorations",
     "sprite": "sLibraryBG_9.png", "cost": 90, "kind": "background"},
    {"id": "bg_orange_stripes", "name": "Orange Stripes", "category": "decorations",
     "sprite": "sLibraryBG_0.png", "cost": 60, "kind": "background"},
    {"id": "bg_green_stripes", "name": "Green Stripes", "category": "decorations",
     "sprite": "sLibraryBG_1.png", "cost": 60, "kind": "background"},
    {"id": "bg_teal_check", "name": "Teal Check", "category": "decorations",
     "sprite": "sLibraryBG_2.png", "cost": 70, "kind": "background"},
    {"id": "bg_blue_check", "name": "Blue Check", "category": "decorations",
     "sprite": "sLibraryBG_3.png", "cost": 70, "kind": "background"},
]
