import pcbnew
import wx
import traceback
import os


PLUGIN_NAME = "Orimin PCB Converter"
PLUGIN_DESC = "Orimin PCBで取り込める形式にするために、スルーホールのランド統一とベタGNDの疑似ベタ（配線）化を行います。"

# Default Parameters
DEFAULT_NET_NAME = "GND"
DEFAULT_TRACK_WIDTH_MM = 0.1

# ベタ塗りつぶし時のスキャン間隔の係数 (1.0 = 隙間なし, 0.8 = 配線幅の80%ごとに配線を引く[20%の重なり])
ZONE_FILL_STEP_RATIO = 0.8

# KiCad Internal Units (1 mm = 1,000,000 IU)
IU_PER_MM = 1000000

# Pad Shapes
SHAPE_CIRCLE = pcbnew.PAD_SHAPE_CIRCLE
SHAPE_OVAL = pcbnew.PAD_SHAPE_OVAL

# UI Constants
UI_WINDOW_SIZE_X = 550
UI_WINDOW_SIZE_Y = 600
UI_BORDER_SIZE = 8

LABEL_SETTINGS = "設定項目（Settings）"
LABEL_PAD_UNIFY = "ランド形状修正を実施"
LABEL_ZONE_CONVERT = "疑似ベタ化を実施（保存して閉じちゃうと戻せないので注意！）"
LABEL_NET_NAME = "疑似ベタ化: 対象ネット名"
LABEL_TRACK_WIDTH = "疑似ベタ化: 配線幅 [mm]:"
LABEL_CONVERT_BTN = "変換！！"

LOG_START_PAD = "=== ランド統一処理を開始します ==="
LOG_START_ZONE = "=== ベタ領域変換処理を開始します ==="
LOG_COMPLETED = "=== 処理完了 ==="
LOG_DIVIDER = "-" * 40
# ==========================================

class ConverterDialog(wx.Dialog):
    def __init__(self, parent):
        super(ConverterDialog, self).__init__(
            parent, title=PLUGIN_NAME, size=(UI_WINDOW_SIZE_X, UI_WINDOW_SIZE_Y),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self.board = pcbnew.GetBoard()

        self.panel = wx.Panel(self)
        self.vbox = wx.BoxSizer(wx.VERTICAL)

        # --- 設定項目 (Settings) ---
        sb = wx.StaticBox(self.panel, label=LABEL_SETTINGS)
        sbs = wx.StaticBoxSizer(sb, wx.VERTICAL)

        # ランド統一 CheckBox
        self.cb_pad_unify = wx.CheckBox(self.panel, label=LABEL_PAD_UNIFY)
        self.cb_pad_unify.SetValue(True)
        sbs.Add(self.cb_pad_unify, flag=wx.ALL, border=UI_BORDER_SIZE)

        # ベタ変換 CheckBox
        self.cb_zone_convert = wx.CheckBox(self.panel, label=LABEL_ZONE_CONVERT)
        self.cb_zone_convert.SetValue(True)
        sbs.Add(self.cb_zone_convert, flag=wx.ALL, border=UI_BORDER_SIZE)

        # ベタ変換 詳細設定 (Grid)
        grid = wx.FlexGridSizer(2, 2, UI_BORDER_SIZE, UI_BORDER_SIZE)
        grid.AddGrowableCol(1, 1)

        # --- ネット名選択 (ComboBox) ---
        grid.Add(wx.StaticText(self.panel, label=LABEL_NET_NAME), 0, wx.ALIGN_CENTER_VERTICAL)

        # 基板からネット名の一覧を取得
        net_names = self.get_net_names()
        self.combo_net_name = wx.ComboBox(self.panel, choices=net_names, style=wx.CB_DROPDOWN | wx.CB_READONLY)

        # デフォルト値の設定
        if DEFAULT_NET_NAME in net_names:
            self.combo_net_name.SetValue(DEFAULT_NET_NAME)
        elif net_names:
            self.combo_net_name.SetSelection(0)

        grid.Add(self.combo_net_name, 1, wx.EXPAND)

        # --- 配線幅設定 ---
        grid.Add(wx.StaticText(self.panel, label=LABEL_TRACK_WIDTH), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_track_width = wx.TextCtrl(self.panel, value=str(DEFAULT_TRACK_WIDTH_MM))
        grid.Add(self.txt_track_width, 1, wx.EXPAND)

        sbs.Add(grid, flag=wx.ALL | wx.EXPAND, border=UI_BORDER_SIZE)
        self.vbox.Add(sbs, flag=wx.ALL | wx.EXPAND, border=UI_BORDER_SIZE)

        # --- コマンドライン風ログ画面 ---
        self.txt_log = wx.TextCtrl(self.panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
        self.txt_log.SetBackgroundColour(wx.Colour(30, 30, 30))
        self.txt_log.SetForegroundColour(wx.Colour(200, 200, 200))
        font = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.txt_log.SetFont(font)

        self.vbox.Add(self.txt_log, proportion=1, flag=wx.ALL | wx.EXPAND, border=UI_BORDER_SIZE)

        # --- 変換！ボタン ---
        self.btn_convert = wx.Button(self.panel, label=LABEL_CONVERT_BTN, size=(-1, 40))
        font_btn = wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.btn_convert.SetFont(font_btn)
        self.btn_convert.Bind(wx.EVT_BUTTON, self.on_convert)
        self.vbox.Add(self.btn_convert, flag=wx.ALL | wx.EXPAND, border=UI_BORDER_SIZE)

        self.panel.SetSizer(self.vbox)

    def get_net_names(self):
        """基板から有効なネット名の一覧を取得してソートして返す"""
        net_info = self.board.GetNetInfo()
        nets = net_info.NetsByNetcode()
        # 空のネット名を除外してリスト化
        names = [net.GetNetname() for net in nets.values() if net.GetNetname()]
        return sorted(list(set(names))) # 重複排除してソート

    def log(self, msg):
        self.txt_log.AppendText(msg + "\n")
        self.txt_log.ShowPosition(self.txt_log.GetLastPosition())
        wx.Yield()

    def on_convert(self, event):
        self.btn_convert.Disable()
        try:
            run_conversion(self)
        except Exception as e:
            self.log("エラーが発生しました: " + str(e))
            self.log(traceback.format_exc())
        finally:
            self.btn_convert.Enable()

# ==========================================
# LOGIC FUNCTIONS
# ==========================================

def run_conversion(dlg):
    board = dlg.board

    do_pad = dlg.cb_pad_unify.GetValue()
    do_zone = dlg.cb_zone_convert.GetValue()
    net_name = dlg.combo_net_name.GetValue().strip()

    try:
        track_width_mm = float(dlg.txt_track_width.GetValue())
    except ValueError:
        dlg.log("Error: 配線幅の入力が不正です。数値を入力してください。")
        return

    track_width_iu = int(track_width_mm * IU_PER_MM)

    if do_pad:
        dlg.log(LOG_START_PAD)
        unify_pads(board, dlg)
        dlg.log(LOG_DIVIDER)

    if do_zone:
        if not net_name:
            dlg.log("Error: 対象ネットが選択されていません。")
        else:
            dlg.log(LOG_START_ZONE)
            convert_zones(board, net_name, track_width_iu, dlg)
            dlg.log(LOG_DIVIDER)

    dlg.log(LOG_COMPLETED)
    pcbnew.Refresh()

def unify_pads(board, dlg):
    target_shapes = (SHAPE_CIRCLE, SHAPE_OVAL)
    global_stats = {}

    footprints = board.GetFootprints()
    for fp in footprints:
        for pad in fp.Pads():
            if pad.GetShape() in target_shapes:
                drill = pad.GetDrillSize()
                key_drill = (drill.x, drill.y)
                size = pad.GetSize()
                shape_params = (pad.GetShape(), size.x, size.y)

                if key_drill not in global_stats:
                    global_stats[key_drill] = {}
                stats = global_stats[key_drill]
                stats[shape_params] = stats.get(shape_params, 0) + 1

    changed_count = 0
    forced_count = 0
    for fp in footprints:
        for pad in fp.Pads():
            if pad.GetShape() not in target_shapes:
                drill = pad.GetDrillSize()
                key_drill = (drill.x, drill.y)
                if key_drill in global_stats:
                    stats = global_stats[key_drill]
                    best_params = max(stats, key=stats.get)
                    new_shape, sz_x, sz_y = best_params
                    pad.SetShape(new_shape)
                    pad.SetSize(pcbnew.VECTOR2I(sz_x, sz_y))
                    changed_count += 1
                else:
                    # フットプリント内に円形/長円形がない場合、強制的に円形に変換
                    size = pad.GetSize()
                    pad.SetShape(SHAPE_CIRCLE)
                    pad.SetSize(size)
                    forced_count += 1
                    lib_name = fp.GetFPID().GetLibNickname()
                    net_name = pad.GetNetname() if hasattr(pad, "GetNetname") else ""
                    dlg.log(f"Warning: ライブラリ '{lib_name}' / ネット '{net_name}' のパッドには参照できる円形/長円形ランドがありません。強制的に円形に変換しました。")

    dlg.log(f"-> {changed_count} 個の四角形ランドを円形/長円形に変換しました。")
    if forced_count > 0:
        dlg.log(f"-> Warning: {forced_count} 個のランドを強制的に円形に変換しました。")

def get_intersections(edges, Y):
    xs = []
    Y_calc = Y + 0.1
    for (p1, p2) in edges:
        x1, y1 = p1.x, p1.y
        x2, y2 = p2.x, p2.y
        if (y1 <= Y_calc < y2) or (y2 <= Y_calc < y1):
            if y2 == y1: continue
            x = x1 + (x2 - x1) * (Y_calc - y1) / (y2 - y1)
            xs.append(x)
    xs.sort()
    return xs

def convert_zones(board, target_net_name, track_width_iu, dlg):
    dlg.log("ベタ領域の計算(Fill)を行っています...")
    filler = pcbnew.ZONE_FILLER(board)
    zones = board.Zones()
    filler.Fill(zones)

    zones_to_remove = []
    y_step_iu = int(track_width_iu * ZONE_FILL_STEP_RATIO)
    if y_step_iu <= 0: y_step_iu = 1

    for zone in zones:
        if zone.GetNetname() == target_net_name:
            if hasattr(zone, 'GetFirstLayer'):
                layer = zone.GetFirstLayer()
            else:
                layer = zone.GetLayer()

            net_code = zone.GetNetCode()
            layer_name = board.GetLayerName(layer)

            if hasattr(zone, 'GetFilledPolysList'):
                try: polys = zone.GetFilledPolysList(layer)
                except TypeError: polys = zone.GetFilledPolysList()
            else:
                polys = zone.GetFilledPolygons()

            if polys.OutlineCount() == 0:
                dlg.log(f"-> Zone (Layer: {layer_name}) は塗りつぶされていないためスキップします。")
                continue

            dlg.log(f"-> Zone (Layer: {layer_name}) を処理中...")

            # --- グループの作成 ---
            new_group = pcbnew.PCB_GROUP(board)
            new_group.SetName(f"Pseudo-Zone_{target_net_name}_{layer_name}")
            board.Add(new_group)

            bbox = polys.BBox()
            y_min, y_max = bbox.GetY(), bbox.GetBottom()
            edges = []

            # 外枠と穴の抽出
            for i in range(polys.OutlineCount()):
                parts = [polys.Outline(i)]
                for h in range(polys.HoleCount(i)):
                    parts.append(polys.Hole(i, h))

                for part in parts:
                    pts = [part.CPoint(j) for j in range(part.PointCount())]
                    for j in range(len(pts)):
                        p1, p2 = pts[j], pts[(j + 1) % len(pts)]
                        edges.append((p1, p2))
                        track = pcbnew.PCB_TRACK(board)
                        track.SetStart(p1); track.SetEnd(p2); track.SetWidth(track_width_iu)
                        track.SetLayer(layer); track.SetNetCode(net_code)
                        board.Add(track)
                        new_group.AddItem(track) # グループに追加

            # スキャンラインによる内側塗りつぶし
            y_current = y_min + track_width_iu / 2
            while y_current <= y_max:
                xs = get_intersections(edges, y_current)
                for k in range(0, len(xs) - 1, 2):
                    track = pcbnew.PCB_TRACK(board)
                    track.SetStart(pcbnew.VECTOR2I(int(xs[k]), int(y_current)))
                    track.SetEnd(pcbnew.VECTOR2I(int(xs[k+1]), int(y_current)))
                    track.SetWidth(track_width_iu); track.SetLayer(layer); track.SetNetCode(net_code)
                    board.Add(track)
                    new_group.AddItem(track) # グループに追加
                y_current += y_step_iu

            # zones_to_remove.append(zone)

    for zone in zones_to_remove:
        board.Remove(zone)
    dlg.log(f"-> 合計 {len(zones_to_remove)} 個のZoneを変換しました。")

# ==========================================
# PLUGIN REGISTRATION
# ==========================================
class CustomConverterPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = PLUGIN_NAME
        self.category = "Modify PCB"
        self.description = PLUGIN_DESC
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(
            os.path.dirname(__file__),
            "icon.png"
        )

    def Run(self):
        dlg = ConverterDialog(None)
        dlg.ShowModal()
        dlg.Destroy()

CustomConverterPlugin().register()