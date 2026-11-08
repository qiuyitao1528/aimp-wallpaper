# AIMP 探针结果

## 1. 窗口
FindWindow(AIMP2_RemoteInfo) = 0xd0878

## 2. 属性 GET（SendMessage 返回值）
  VERSION      = 35392167 (0x021C0AA7) hi=540 lo=2727
  STATE        = 2 (0x00000002) hi=0 lo=2
  POSITION_ms  = 281079 (0x000449F7) hi=4 lo=18935
  DURATION_ms  = 286040 (0x00045D58) hi=4 lo=23896
  VOLUME       = 75 (0x0000004B) hi=0 lo=75
  MUTE         = 0 (0x00000000) hi=0 lo=0

## 3. 共享内存
  OpenFileMapping(AIMP2_RemoteInfo) = OK
  OpenFileMapping(AIMP_RemoteInfo) = 无
  OpenFileMapping(AIMP_FileInfo) = 无
  OpenFileMapping(AIMP2_FileInfo) = 无
  实际可读 2048 字节
  使用映射名：AIMP2_RemoteInfo
  前 160 字节：
  0000: 58 00 00 00 FF FF FF FF 31 03 00 00 02 00 00 00  X.......1.......
  0010: 58 5D 04 00 13 DB C4 01 00 00 00 00 00 00 00 00  X]..............
  0020: 80 BB 00 00 01 00 00 00 0C 00 00 00 04 00 00 00  ................
  0030: 04 00 00 00 34 00 00 00 00 00 00 00 0C 00 00 00  ....4...........
  0040: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
  0050: 00 00 00 00 00 00 00 00 22 59 6E 6D 4B 6A 2D 00  ........"YnmKj-.
  0060: E6 30 E1 30 CE 30 A6 30 AD 30 CF 30 B7 30 2D 00  .0.0.0.0.0.0.0-.
  0070: 52 97 28 67 7D 96 DC 83 32 00 30 00 32 00 34 00  R.(g}...2.0.2.4.
  0080: 45 00 3A 00 5C 00 4F 00 72 00 69 00 67 00 69 00  E.:.\.O.r.i.g.i.
  0090: 6E 00 61 00 6C 00 20 00 53 00 6F 00 75 00 6E 00  n.a.l. .S.o.u.n.
  UTF-16 可读段（偏移: 文本）：
    0x0058: '夢浮橋-ユメノウキハシ-青木陽菜2024E:\\Original Sound Track\\Music\\夢浮橋-ユメノウキハシ--青木陽菜.flac夢浮橋-ユメノウキハシ-'
  DWORD@0x00 = 88 (0x00000058)
  DWORD@0x04 = 4294967295 (0xFFFFFFFF)
  DWORD@0x08 = 817 (0x00000331)
  DWORD@0x50 = 0 (0x00000000)
  DWORD@0x54 = 0 (0x00000000)
  DWORD@0x58 = 1835948322 (0x6D6E5922)

## 4. 通知 + 封面（建接收窗口）
  接收窗口 = 0x130a48
  REGISTER_NOTIFY -> 0
  [COPYDATA] dwData=0x41495043 cbData=5357186
  GET_ALBUMART -> 1
  [NOTIFY] wParam=3 lParam=32
  [NOTIFY] wParam=3 lParam=32
  [NOTIFY] wParam=3 lParam=32
  通知收到 3 条：[(3, 32), (3, 32), (3, 32)]
  封面收到 = True，5357186 字节 -> E:\aimp-wallpaper\scripts\cover_probe.img