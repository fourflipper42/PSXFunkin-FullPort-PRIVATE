#include "menu.h"
#include "menu_art.h"
#include "main.h"
#include "timer.h"
#include "io.h"
#include "gfx.h"
#include "audio.h"
#include "pad.h"
#include "archive.h"
#include "mem.h"
#include "trans.h"
#include "loadscr.h"
#include "stage.h"

#include "menu_intro_generated.h"

static const struct
			{
				const char *week;
				StageId stage;
				const char *name;
				const char *tracks[4];
			} weeks[] = {
				{NULL, StageId_1_4, "TUTORIAL", {"TUTORIAL", NULL, NULL}},
				{"1", StageId_1_1, "DADDY DEAREST", {"BOPEEBO", "FRESH", "DADBATTLE"}},
				{"2", StageId_2_1, "SPOOKY MONTH", {"SPOOKEEZ", "SOUTH", "MONSTER"}},
				{"3", StageId_3_1, "PICO", {"PICO", "PHILLY NICE", "BLAMMED"}},
				{"4", StageId_4_1, "MOMMY MUST MURDER", {"SATIN PANTIES", "HIGH", "MILF"}},
				{"5", StageId_5_1, "RED SNOW", {"COCOA", "EGGNOG", "WINTER HORRORLAND"}},
				{"6", StageId_6_1, "HATING SIMULATOR", {"SENPAI", "ROSES", "THORNS"}},
				{"7", StageId_7_1, "TANKMAN", {"UGH", "GUNS", "STRESS"}},
				{"8", StageId_8_1, "DUE DEBTS", {"DARNELL", "LIT UP", "TWO HOT", "BLAZIN'"}},
			};
static const struct
			{
				StageId stage;
				const char *text;
			} songs[] = {
				//{StageId_4_4, "TEST"},
				{StageId_1_4, "TUTORIAL"},
				{StageId_1_1, "BOPEEBO"},
				{StageId_1_2, "FRESH"},
				{StageId_1_3, "DADBATTLE"},
				{StageId_2_1, "SPOOKEEZ"},
				{StageId_2_2, "SOUTH"},
				{StageId_2_3, "MONSTER"},
				{StageId_3_1, "PICO"},
				{StageId_3_2, "PHILLY NICE"},
				{StageId_3_3, "BLAMMED"},
				{StageId_4_1, "SATIN PANTIES"},
				{StageId_4_2, "HIGH"},
				{StageId_4_3, "MILF"},
				{StageId_5_1, "COCOA"},
				{StageId_5_2, "EGGNOG"},
				{StageId_5_3, "WINTER HORRORLAND"},
				{StageId_6_1, "SENPAI"},
				{StageId_6_2, "ROSES"},
				{StageId_6_3, "THORNS"},
				{StageId_7_1, "UGH"},
				{StageId_7_2, "GUNS"},
				{StageId_7_3, "STRESS"},
				{StageId_8_1, "DARNELL"},
				{StageId_8_2, "LIT UP"},
				{StageId_8_3, "TWO HOT"},
				{StageId_8_4, "BLAZIN'"},
			};
static struct {
    MenuPage page, next_page;
    boolean page_swap;
    u8 select, next_select, funny_message;
    StageId stage_id;
    StageDiff difficulty;
    boolean story;
    fixed_t credits_scroll;
    Gfx_Tex tex_ng;
} menu;

static void Go(MenuPage page, int selection)
{
    menu.next_page = page;
    menu.next_select = selection;
    Trans_Start();
}
static boolean InputReady(void) { return menu.next_page == menu.page && Trans_Idle(); }
static void Select(int count)
{
    if (pad_state.press & PAD_UP) menu.select = (menu.select + count - 1) % count;
    else if (pad_state.press & PAD_DOWN) menu.select = (menu.select + 1) % count;
}
static void Difficulty(StageId id, boolean extra)
{
    /* Revalidate after changing songs, before accepting Start in that frame. */
    if (!Stage_SupportsDifficulty(id, menu.difficulty)) menu.difficulty = StageDiff_Normal;
    if (pad_state.press & (PAD_LEFT | PAD_RIGHT)) {
        int count = extra ? StageDiff_Max : StageDiff_Hard + 1;
        int direction = (pad_state.press & PAD_RIGHT) ? 1 : -1;
        int tries = 0;
        do {
            menu.difficulty = (menu.difficulty + count + direction) % count;
        } while (!Stage_SupportsDifficulty(id, menu.difficulty) && ++tries < count);
    }
}
static void DrawDifficulty(void)
{
    static const char *names[] = {"< EASY >", "< NORMAL >", "< HARD >", "< ERECT >", "< NIGHTMARE >"};
    MenuArt_Text(names[menu.difficulty], 160, 196, 1, 1);
}
static void Play(StageId id, boolean story)
{
    menu.stage_id = id;
    menu.story = story;
    Go(MenuPage_Stage, 0);
}
static void Footer(void) { MenuArt_Text("X / START: PLAY    O: BACK", 160, 216, 1, 1); }
void Menu_Load(MenuPage page)
{
    IO_Data arc = IO_Read("\\MENU\\MENU.ARC;1");
    Gfx_LoadTex(&menu.tex_ng, Archive_Find(arc, "ng.tim"), 0);
    Mem_Free(arc);
    MenuArt_Load();
    menu.select = menu.next_select = 0;
    menu.page = menu.next_page = page;
    menu.funny_message = ((*((volatile u32*)0xBF801120)) >> 3) % COUNT_OF(funny_messages);
    menu.page_swap = true;
    menu.difficulty = StageDiff_Normal;
    Trans_Clear();
    stage.song_step = 0;
    Audio_PlayXA_Track(XA_GettinFreaky, 0x40, 0, 1);
    Audio_WaitPlayXA();
    Gfx_SetClear(0, 0, 0);
}
void Menu_Unload(void) { MenuArt_Free(); }
void Menu_Tick(void)
{
    unsigned int song_ms = Audio_TellXA_Milli();
    MenuPage exec_page;
    stage.song_step = song_ms * 102 / 15000;
    if (Trans_Tick()) {
        menu.page = menu.next_page;
        menu.select = menu.next_select;
        menu.page_swap = true;
    }
    if (menu.page_swap) {
        MenuArt_Enter();
        menu.credits_scroll = 0;
        if (menu.page == MenuPage_Story || menu.page == MenuPage_Freeplay)
            menu.difficulty = StageDiff_Normal;
    }
    switch (exec_page = menu.page) {
		case MenuPage_Opening:
		{
			u16 beat = stage.song_step >> 2;

			//Start title screen if opening ended
			if (beat >= 16)
			{
				menu.page = menu.next_page = MenuPage_Title;
				menu.page_swap = true;
				//Fallthrough
			}
			else
			{
				//Start title screen if start pressed
				if (pad_state.held & PAD_START)
					menu.page = menu.next_page = MenuPage_Title;

				//Draw different text depending on beat
				RECT src_ng = {0, 0, 128, 128};
				const char *const *funny_message = funny_messages[menu.funny_message];

				switch (beat)
				{
					case 3:
						MenuArt_Text("PRESENT", SCREEN_WIDTH2, SCREEN_HEIGHT2 + 32, 1, 1);
				//Fallthrough
					case 2:
					case 1:
                        MenuArt_Text("THE", 160, 80, 1, 1);
                        MenuArt_Text("FUNKIN CREW INC", 160, 104, 1, 1);
						break;

					case 7:
						MenuArt_Text("NEWGROUNDS", SCREEN_WIDTH2, SCREEN_HEIGHT2 - 32, 1, 1);
						Gfx_BlitTex(&menu.tex_ng, &src_ng, (SCREEN_WIDTH - 128) >> 1, SCREEN_HEIGHT2 - 16);
				//Fallthrough
					case 6:
					case 5:
						MenuArt_Text("IN ASSOCIATION", SCREEN_WIDTH2, SCREEN_HEIGHT2 - 64, 1, 1);
						MenuArt_Text("WITH", SCREEN_WIDTH2, SCREEN_HEIGHT2 - 48, 1, 1);
						break;

					case 11:
						MenuArt_Text(funny_message[1], SCREEN_WIDTH2, SCREEN_HEIGHT2, 1, 1);
				//Fallthrough
					case 10:
					case 9:
						MenuArt_Text(funny_message[0], SCREEN_WIDTH2, SCREEN_HEIGHT2 - 16, 1, 1);
						break;

					case 15:
						MenuArt_Text("FUNKIN", SCREEN_WIDTH2, SCREEN_HEIGHT2 + 8, 1, 1);
				//Fallthrough
					case 14:
						MenuArt_Text("NIGHT", SCREEN_WIDTH2, SCREEN_HEIGHT2 - 8, 1, 1);
				//Fallthrough
					case 13:
						MenuArt_Text("FRIDAY", SCREEN_WIDTH2, SCREEN_HEIGHT2 - 24, 1, 1);
						break;
				}
				break;
			}
		}
	//Fallthrough
        case MenuPage_Title:
        {
            if (InputReady() && (pad_state.press & PAD_START)) Go(MenuPage_Main, 0);
            MenuArt_Text("PRESS START TO BEGIN", 160, 208, 1, (song_ms / 300) & 1);
            MenuArt_Title(song_ms);
            break;
        }
        case MenuPage_Main:
        {
            static const MenuPage pages[] = {MenuPage_Story, MenuPage_Freeplay, MenuPage_Merch, MenuPage_Options, MenuPage_Credits};
            if (InputReady()) {
                Select(COUNT_OF(pages));
                if (pad_state.press & PAD_CIRCLE) Go(MenuPage_Title, 0);
                else if (pad_state.press & (PAD_CROSS | PAD_START)) Go(pages[menu.select], 0);
            }
            MenuArt_Tick(menu.select);
            for (int i = 0; i < COUNT_OF(pages); i++)
                MenuArt_Label(i, menu.select == i, 160, 35 + i * 42);
            MenuArt_Back();
            break;
        }
        case MenuPage_Story:
        {
            if (InputReady()) {
                Select(COUNT_OF(weeks));
                Difficulty(weeks[menu.select].stage, false);
                if (pad_state.press & PAD_CIRCLE) Go(MenuPage_Main, 0);
                else if (pad_state.press & (PAD_CROSS | PAD_START)) Play(weeks[menu.select].stage, true);
            }
            MenuArt_Text("STORY MODE", 160, 16, 1, 1);
            MenuArt_Text(weeks[menu.select].name, 160, 44, 1, 1);
            if (!menu.select) MenuArt_Text("TUTORIAL", 160, 68, 1, 1);
            else {
                char label[32];
                sprintf(label, "< %s %s >", menu.select == 8 ? "WEEKEND" : "WEEK", menu.select == 8 ? "1" : weeks[menu.select].week);
                MenuArt_Text(label, 160, 68, 1, 1);
            }
            for (int i = 0; i < COUNT_OF(weeks[menu.select].tracks); i++)
                MenuArt_Text(weeks[menu.select].tracks[i], 160, 98 + i * 20, 1, 1);
            MenuArt_Text("UP / DOWN: SELECT WEEK", 160, 174, 1, 1);
            DrawDifficulty(); Footer(); MenuArt_Back();
            break;
        }
        case MenuPage_Freeplay:
        {
            if (InputReady()) {
                Select(COUNT_OF(songs));
                Difficulty(songs[menu.select].stage, true);
                if (pad_state.press & PAD_CIRCLE) Go(MenuPage_Main, 1);
                else if (pad_state.press & (PAD_CROSS | PAD_START)) Play(songs[menu.select].stage, false);
            }
            MenuArt_Text("FREEPLAY", 160, 16, 1, 1);
            for (int offset = -3; offset <= 3; offset++) {
                int i = (int)menu.select + offset;
                if (i < 0 || i >= COUNT_OF(songs)) continue;
                MenuArt_Text(songs[i].text, 160, 110 + offset * 22, 1, !offset);
                if (!offset) {
                    RECT bar = {12, 108, 296, 16};
                    Gfx_DrawRect(&bar, 69, 30, 96);
                }
            }
            DrawDifficulty(); Footer(); MenuArt_Back();
            break;
        }
        case MenuPage_Options:
        {
            static const struct { const char *text; boolean *value; } options[] = {
                {"INTERPOLATION", &stage.expsync}, {"KADE INPUT", &stage.kade},
                {"GHOST TAP", &stage.ghost}, {"DOWNSCROLL", &stage.downscroll}
            };
            if (InputReady()) {
                Select(COUNT_OF(options));
                if (pad_state.press & PAD_CIRCLE) Go(MenuPage_Main, 3);
                else if (pad_state.press & (PAD_CROSS | PAD_LEFT | PAD_RIGHT)) *options[menu.select].value ^= 1;
            }
            MenuArt_Text("OPTIONS", 160, 20, 1, 1);
            for (int i = 0; i < COUNT_OF(options); i++) {
                char label[48];
                sprintf(label, "%c %s: %s", menu.select == i ? '>' : ' ', options[i].text, *options[i].value ? "ON" : "OFF");
                MenuArt_Text(label, 28, 64 + i * 30, 0, menu.select == i);
            }
            MenuArt_Text("LEFT / RIGHT: CHANGE  O: BACK", 160, 216, 1, 1);
            MenuArt_Back();
            break;
        }
        case MenuPage_Credits:
        {
            fixed_t limit = (MenuArt_CreditCount() > 13 ? MenuArt_CreditCount() - 13 : 0) * FIXED_DEC(12,1);
            if (InputReady()) {
                if (pad_state.press & PAD_CIRCLE) Go(MenuPage_Main, 4);
                if (pad_state.held & PAD_DOWN) menu.credits_scroll += timer_dt * 72;
                if (pad_state.held & PAD_UP) menu.credits_scroll -= timer_dt * 72;
                if (pad_state.press & PAD_RIGHT) menu.credits_scroll += FIXED_DEC(144,1);
                if (pad_state.press & PAD_LEFT) menu.credits_scroll -= FIXED_DEC(144,1);
                if (menu.credits_scroll < 0) menu.credits_scroll = 0;
                if (menu.credits_scroll > limit) menu.credits_scroll = limit;
            }
            MenuArt_Text("CREDITS", 160, 16, 1, 1);
            for (unsigned int i = 0; i < MenuArt_CreditCount(); i++) {
                int y = 40 + i * 12 - (menu.credits_scroll >> FIXED_SHIFT);
                if (y >= 40 && y <= 196) MenuArt_Text(MenuArt_Credit(i), 16, y, 0, 1);
            }
            MenuArt_Text("UP/DOWN: SCROLL  O: BACK", 160, 216, 1, 1);
            MenuArt_Back();
            break;
        }
        case MenuPage_Merch:
            if (InputReady() && (pad_state.press & PAD_CIRCLE)) Go(MenuPage_Main, 2);
            MenuArt_Text("OFFICIAL FUNKIN' MERCH", 160, 48, 1, 1);
            MenuArt_Text("VISIT ON YOUR PHONE OR COMPUTER", 160, 88, 1, 1);
            MenuArt_Text("needlejuicerecords.com", 160, 116, 1, 1);
            MenuArt_Text("/en-ca/pages/friday-night-funkin", 160, 132, 1, 1);
            MenuArt_Text("O: BACK", 160, 216, 1, 1);
            MenuArt_Back();
            break;
        case MenuPage_Stage:
            Menu_Unload();
            LoadScr_Start();
            Stage_Load(menu.stage_id, menu.difficulty, menu.story);
            gameloop = GameLoop_Stage;
            LoadScr_End();
            break;
        default: break;
    }
    menu.page_swap = menu.page != exec_page;
}
