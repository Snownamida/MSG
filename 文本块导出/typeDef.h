#define block_start 0x8000
#define block_end 0x8B57
#define sentance_total 2781
#define sentance_pointer_start 0x1CC5

#define IS_DOUBLE_BYTE(X) ((X) == 0x05 || (X) == 0x07 || (X) == 0x0B || (X) == 0x0C || (X) == 0x13 || (X) == 0x14 || (X) == 0x16 || (X) == 0x18 || (X) >= 0x80)
#define IS_TRIPLE_BYTE(X) ((X) == 0x0F || (X) == 0x10 || (X) == 0x12 || (X) == 0x17)

struct threeByte {
	unsigned char byte1;
	unsigned char byte2;
	unsigned char byte3;
};

struct string {
	unsigned char string[2048];
	int length;
};

struct pointer_with_length {
	int pointer;
	int length;
};
