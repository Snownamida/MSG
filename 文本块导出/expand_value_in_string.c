//**************************************串内数值进行替换**************************************
#pragma warning(disable:4996)
#include <stdlib.h>
#include<stdio.h>
#include "typeDef.h"
#include "unreference.h"
#include "value_calculate.h"

char char_ppu_to_unicode[0x100][16] = {
	"(00)",		"(01)",		"(02)",		"(03)",		"(04)",		"！",			"！！",		"？",			"！？",		"(冒汗)",	"%",			"/",			"ー",			"..",		"゛",			"゜",
	".",			"「",			"」",			"“",			"”",			"(特1)",		"(特2)",		"|",			"(特3)",		"(爱心)",	"★",			"(音符)",	"方",			"本",			"名",			"明",
	"0",			"1",			"2",			"3",			"4",			"5",			"6",			"7",			"8",			"9",			"A",			"B",			"C",			"D",			"E",			"F",
	"G",			"H",			"I",			"J",			"K",			"L",			"M",			"N",			"O",			"P",			"Q",			"R",			"S",			"T",			"U",			"V",
	"W",			"X",			"Y",			"Z",			"ァ",			"ィ",			"ェ",			"ォ",			"ッ",			"ャ",			"ュ",			"ョ",			"っ",			"ゃ",			"ゅ",			"ょ",
	"あ",			"い",			"う",			"え",			"お",			"か",			"き",			"く",			"け",			"こ",			"さ",			"し",			"す",			"せ",			"そ",			"た",
	"ち",			"つ",			"て",			"と",			"な",			"に",			"ぬ",			"ね",			"の",			"は",			"ひ",			"ふ",			"へ",			"ほ",			"ま",			"み",
	"む",			"め",			"も",			"や",			"ゆ",			"よ",			"ら",			"り",			"る",			"れ",			"ろ",			"わ",			"を",			"ん",			"目",			"夜",
	"ア",			"イ",			"ウ",			"エ",			"オ",			"カ",			"キ",			"ク",			"ケ",			"コ",			"サ",			"シ",			"ス",			"セ",			"ソ",			"タ",
	"チ",			"ツ",			"テ",			"ト",			"ナ",			"ニ",			"ヌ",			"ネ",			"ノ",			"ハ",			"ヒ",			"フ",			"ヘ",			"ホ",			"マ",			"ミ",
	"ム",			"メ",			"モ",			"ヤ",			"ユ",			"ヨ",			"ラ",			"リ",			"ル",			"レ",			"ロ",			"ワ",			"ヲ",			"ン",			"用",			"（了）",
	"々",			"以",			"井",			"宇",			"央",			"下",			"化",			"何",			"可",			"回",			"外",			"核",			"危",			"机",			"気",			"休",
	"居",			"况",			"区",			"空",			"兄",			"月",			"光",			"向",			"灰",			"行",			"合",			"今",			"才",			"在",			"作",			"子",
	"志",			"死",			"私",			"自",			"主",			"手",			"住",			"出",			"所",			"小",			"少",			"床",			"泊",			"照",			"上",			"（伏）",
	"心",			"人",			"生",			"先",			"全",			"体",			"对",			"知",			"中",			"宙",			"忠",			"日",			"的",			"天",			"当",			"同",
	"内",			"入",			"任",			"年",			"発",			"反",			"不",			"父",			"武",			"分",			"兵",			"法",			"(FC)",		"(FD)",		" ",	"(FF)"
};

char char_ppu_to_unicode_ba[0x100][16] = {
	[0x82] = "ヴ",
	[0x55] = "が",		"ぎ",		"ぐ",		"げ",		"ご",		"ざ",		"じ",		"ず",		"ぜ",		"ぞ",		"だ",		"ぢ",		"づ",		"で",		"ど",
	[0x85] = "ガ",		"ギ",		"グ",		"ゲ",		"ゴ",		"ザ",		"ジ",		"ズ",		"ゼ",		"ゾ",		"ダ",		"ヂ",		"ヅ",		"デ",		"ド",
	[0x69] = "ば",		"び",		"ぶ",		"べ",		"ぼ",
	[0x99] = "バ",		"ビ",		"ブ",		"ベ",		"ボ"
};

char char_ppu_to_unicode_pa[0x100][16] = {
	[0x69] = "ぱ",		"ぴ",		"ぷ",		"ぺ",		"ぽ",
	[0x99] = "パ",		"ピ",		"プ",		"ぺ",		"ポ"
};

struct string block_to_string_ppu(int block) {												//跨级工程
	int text_pointer = block_to_text_pointer(block);
	struct threeByte text = unreference_text_pointer(text_pointer);
	struct pointer_with_length string_ppu_pointer = text_to_string_pointer(text);
	struct string string_ppu = unreference_string_pointer(string_ppu_pointer);
	return string_ppu;
}

struct string sentance_number_to_block_string(unsigned int sentance_number) {	//跨级工程
	int sentance_pointer = sentance_number_to_sentance_pointer(sentance_number);
	struct threeByte sentance = unreference_sentance_pointer(sentance_pointer);
	int block_string_pointer = sentance_to_block_string_pointer(sentance);
	struct string block_string = unreferernce_block_string_pointer(block_string_pointer);
	return block_string;
}

struct string string_ppu_to_unicode(struct string string_ppu) {
	struct string string_unicode = { .string = { 0 } };
	for (int i = 0; i < string_ppu.length; i++) {
		switch (string_ppu.string[i]) {
		case 0x0E:	//浊音゛
			i++;
			strcat(string_unicode.string, char_ppu_to_unicode_ba[string_ppu.string[i]]);
#ifdef printf("字符串数居然超过了32, 字符串指针为%x的肯定有问题\n", string_pointer);
			if (strcmp(char_ppu_to_unicode_ba[string_ppu.string[i]], ""))printf("有不正确的浊音\n");
#endif // printf("字符串数居然超过了32, 字符串指针为%x的肯定有问题\n", string_pointer);

			break;
		case 0x0F:	//半浊音゜
			i++;
			strcat(string_unicode.string, char_ppu_to_unicode_pa[string_ppu.string[i]]);
#ifdef printf("字符串数居然超过了32, 字符串指针为%x的肯定有问题\n", string_pointer);
			if (strcmp(char_ppu_to_unicode_ba[string_ppu.string[i]], ""))printf("有不正确的半浊音\n");
#endif // printf("字符串数居然超过了32, 字符串指针为%x的肯定有问题\n", string_pointer);
			break;
		case 0x00:	//特殊作用，如人物卡
			i++;
			break;
		default:
			strcat(string_unicode.string, char_ppu_to_unicode[string_ppu.string[i]]);
		}
	}
	return string_unicode;
}



struct string block_string_to_string_ppu(struct string block_string) {
	struct string string_ppu = { .string = {0},.length = 0 };
	for (int block_count = 0; block_count < block_string.length; block_count++) {
		if (IS_TRIPLE_BYTE(block_string.string[block_count])) {
			block_count += 2;
			continue;
		}
		if (IS_DOUBLE_BYTE(block_string.string[block_count]) && block_string.string[block_count] < 0x80) {
			block_count++;
			continue;
		}
		if (block_string.string[block_count] < 0x80) {
			struct string string_ppu_slice = block_to_string_ppu(block_string.string[block_count]);
			for (int i = 0; i < string_ppu_slice.length; i++) {
				string_ppu.string[string_ppu.length + i] = string_ppu_slice.string[i];
			}
			string_ppu.length += string_ppu_slice.length;
			continue;
		}
		if (block_string.string[block_count] >= 0x80) {
			int byte1 = block_string.string[block_count];
			int byte2 = block_string.string[++block_count];
			struct string string_ppu_slice = block_to_string_ppu((byte1 << 8) + byte2);
			for (int i = 0; i < string_ppu_slice.length; i++) {
				string_ppu.string[string_ppu.length + i] = string_ppu_slice.string[i];
			}
			string_ppu.length += string_ppu_slice.length;
			continue;
		}


	}

	return string_ppu;
}

