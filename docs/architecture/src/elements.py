"""Shared definitions for the felis-ai-chatbot architecture diagrams.

Meaning lives here, once: node labels / icons / sizes, frame names, and every edge's
source, target, line type, purpose label and [technology]. The per-diagram layout
(coordinates, label side, edge waypoints and label position) lives in gen.py.
Changing a label or a technology here changes every diagram that draws that element.
"""
from xml.sax.saxutils import escape

FONT = "Helvetica,Arial,IPAPGothic,Hiragino Sans,Yu Gothic,Meiryo,sans-serif"
AZ = "https://app.diagrams.net/img/lib/azure2/"
BLUE, GREY = "#0078D4", "#555555"
C4_PURPOSE_PX, C4_TECH_PX = 19, 17  # C4 style: purpose line / smaller [technology] line

# ---- nodes: id -> (label, icon style, width, height) ----
NODES = {
    "entraIcon": ("", "image;image=" + AZ + "identity/Azure_Active_Directory.svg", 70, 64),
    "appRegistration": ("app registration<br>（Easy Auth 用）", "image;image=" + AZ + "identity/App_Registrations.svg", 63, 64),
    "browser": ("ユーザーの<br>ブラウザ", "image;image=" + AZ + "general/Browser.svg", 80, 64),
    "openai": ("Azure OpenAI<br>chat・embedding<br>デプロイ", "image;image=" + AZ + "ai_machine_learning/Azure_OpenAI.svg", 68, 68),
    "frontend": ("Azure Container Apps<br>frontend（BFF）", "image;image=" + AZ + "other/Worker_Container_App.svg", 68, 66),
    "backend": ("Azure Container Apps<br>backend（RAG API）", "image;image=" + AZ + "other/Worker_Container_App.svg", 68, 66),
    "opsApp": ("Azure Container Apps<br>ops（運用作業用）", "image;image=" + AZ + "other/Worker_Container_App.svg", 68, 66),
    "jobs": ("Azure Container<br>Apps jobs ×4", "image;image=" + AZ + "other/Worker_Container_App.svg", 68, 66),
    "postgres": ("Azure Database for<br>PostgreSQL flexible server<br>pgvector でベクトル検索",
                 "image;image=" + AZ + "databases/Azure_Database_PostgreSQL_Server.svg", 48, 64),
    "identity": ("User-assigned managed identity<br>全アプリ・Job 共通の ID", "image;image=" + AZ + "identity/Managed_Identities.svg", 68, 66),
    "keyVault": ("Azure Key Vault", "image;image=" + AZ + "security/Key_Vaults.svg", 68, 68),
    "privateDns": ("Azure Private DNS zone", "image;image=" + AZ + "networking/DNS_Zones.svg", 64, 64),
    "github": ("GitHub Actions<br>5 分ごとの外形監視", "dashed=0;outlineConnect=0;shape=mxgraph.weblogos.github", 56, 56),
    "developer": ("開発者のローカル環境<br>手動デプロイ・運用操作", "image;image=https://icons.diagrams.net/assets/devices/1/Laptop-29.svg", 80, 80),
    "resourceManager": ("Azure Resource<br>Manager", "image;image=https://icons.diagrams.net/assets/azure/1/Resource_Manager.svg", 48, 48),
    "stateStorage": ("storage account", "image;image=" + AZ + "storage/Storage_Accounts.svg", 65, 52),
    "backupStorage": ("backup storage<br>（Microsoft 管理）<br>保持 7 日・geo-redundant<br>（paired region へ複製）",
                      "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#E8E0F4;strokeColor=#6B3FA0;strokeWidth=1.5", 60, 58),
    "actionGroup": ("action group<br>メール・Azure mobile app<br>へ通知",
                    "shape=mxgraph.ios7.icons.mail;strokeWidth=2;strokeColor=#6B3FA0;fillColor=#FFFFFF;shadow=0;dashed=0", 60, 36),
    "metricAlerts": ("metric alert rules ×5<br>死活・容量<br>CPU クレジット", "image;image=" + AZ + "management_governance/Alerts.svg", 67, 56),
    "logAlert": ("log search alert rule<br>Key Vault references の<br>同期失敗を検知", "image;image=" + AZ + "management_governance/Alerts.svg", 67, 56),
    "logAnalytics": ("Log Analytics<br>workspace<br>保持 30 日", "image;image=" + AZ + "analytics/Log_Analytics_Workspaces.svg", 64, 64),
    "registry": ("Azure Container Registry", "image;image=" + AZ + "containers/Container_Registries.svg", 68, 61),
}

# ---- boxes (not an icon): id -> (label, width, height) ----
BOXES = {
    "builtinAuth": ("<b>built-in<br>authentication</b><br>（Easy Auth）", 140, 110),
}

# ---- frames: kind -> (name, style). Names: English, sentence case, Microsoft Learn wording. No internal names. ----
FRAMES = {
    "rg": ("Resource group", "fillColor=none;strokeColor=#999999;fontSize=17;fontStyle=0;fontColor=#555555;dashed=1;dashPattern=6 4"),
    "vnet": ("Virtual network", "fillColor=#F3FAF3;strokeColor=#2E7D32;fontSize=18;fontStyle=1;fontColor=#2E7D32"),
    "subnet": ("Subnet", "fillColor=#FFFFFF;strokeColor=#2E7D32;fontSize=17;fontStyle=0;fontColor=#2E7D32;dashed=1;dashPattern=6 4"),
    "cae": ("Container Apps environment", "fillColor=#EAF3FC;strokeColor=#0078D4;fontSize=19;fontStyle=1;fontColor=#0078D4"),
    "entra": ("Microsoft Entra ID", "fillColor=#FFFFFF;strokeColor=#0062AD;fontSize=18;fontStyle=1;fontColor=#0062AD"),
    "legend": ("凡例", "fillColor=#FFFFFF;strokeColor=#5B5B5B;fontSize=19;fontStyle=1;fontColor=#5B5B5B"),
}

# frame id -> kind (the same id means the same frame in every diagram)
FRAME_IDS = {
    "entraId": "entra",
    "rgOpenai": "rg",
    "rgMain": "rg",
    "rgState": "rg",
    "vnet": "vnet",
    "subnetApps": "subnet",
    "subnetDb": "subnet",
    "caEnv": "cae",
    "legend": "legend",
}

# ---- edges: id -> (source, target, line type, purpose label, [technology], C4 label form) ----
# line type: "main" = numbered chat request, "other" = other communication, "link" = virtual network link (no arrow)
# Arrow direction is the communication direction (the side that starts it -> the side that receives it).
EDGES = {
    # chat request flow (C4 label form: purpose on line 1, smaller [technology] on line 2)
    "flow1": ("browser", "builtinAuth", "main", "① 画面表示", "HTTPS", True),
    "flow2": ("browser", "entraId", "main", "② サインイン", "OpenID Connect", True),
    "flow3": ("browser", "builtinAuth", "main", "③ 質問の送信", "JSON/HTTPS, SSE", True),
    "authToFront": ("builtinAuth", "frontend", "main", "", None, True),
    "flow4": ("frontend", "backend", "main", "④ 質問の転送", "JSON/HTTP, SSE", True),
    "flow5": ("backend", "openai", "main", "⑤ 質問文の embedding", "HTTPS", True),
    "flow6": ("backend", "postgres", "main", "⑥ 類似度検索", "PostgreSQL protocol/TLS", True),
    "flow7": ("backend", "openai", "main", "⑦ 回答の生成", "HTTPS, SSE", True),
    "token": ("caEnv", "entraId", "other", "managed identity のトークン取得", None, True),
    "kvRefs": ("caEnv", "keyVault", "other", "secret の取得（frontend・backend）", "Key Vault references", True),
    "vnetLink": ("privateDns", "vnet", "link", "", None, True),
    # deployment, operations, monitoring, backup (purpose and means on one label)
    "probe": ("github", "frontend", "other", "/readyz", None, False),
    "probeForward": ("frontend", "backend", "other", "/readyz 転送", None, False),
    "jobStart": ("developer", "jobs", "other", "job start", None, False),
    "exec": ("developer", "opsApp", "other", "exec", None, False),
    "push": ("developer", "registry", "other", "docker push", None, False),
    "apply": ("developer", "resourceManager", "other", "terraform apply", None, False),
    "state": ("developer", "stateStorage", "other", "state の読み書き", None, False),
    "pull": ("caEnv", "registry", "other", "イメージ pull", None, False),
    "embedJob": ("jobs", "openai", "other", "既存文書の embedding 生成", None, False),
    "jobsDb": ("jobs", "postgres", "other", "マイグレーション<br>データ投入・embedding<br>観測値の採取（毎分）", None, False),
    "opsDb": ("opsApp", "postgres", "other", "運用作業", None, False),
    "backup": ("postgres", "backupStorage", "other",
               "automated backups（snapshot）<br>WAL（Microsoft.Storage<br>service endpoint 経由）", None, False),
    "metricEval": ("metricAlerts", "postgres", "other", "platform metrics<br>を評価", None, False),
    "notify1": ("metricAlerts", "actionGroup", "other", "通知", None, False),
    "notify2": ("logAlert", "actionGroup", "other", "通知", None, False),
    "kql": ("logAlert", "logAnalytics", "other", "KQL（15 分ごと）", None, False),
    "diag": ("keyVault", "logAnalytics", "other", "diagnostic setting", None, False),
    "logs": ("caEnv", "logAnalytics", "other", "ログ送信", None, False),
}

# ---- legend text ----
LEGEND = {
    "lgMainText": "①〜⑦ チャット 1 回分の<br>リクエスト（番号順）",
    "lgOtherText": "その他の通信",
    "lgLinkText": "virtual network link",
    "lgNote": "矢印は通信を開始する側 → 受ける側<br>（応答は描かない）",
    "lgOtherOnly": "通信（矢印は開始する側 → 受ける側）",
}

LABEL_POS = {
    "bottom": "verticalLabelPosition=bottom;verticalAlign=top;labelPosition=center;align=center",
    "top": "verticalLabelPosition=top;verticalAlign=bottom;labelPosition=center;align=center",
    "right": "labelPosition=right;align=left;verticalLabelPosition=middle;verticalAlign=middle;spacingLeft=4",
    "left": "labelPosition=left;align=right;verticalLabelPosition=middle;verticalAlign=middle;spacingRight=4",
}


def _q(s):
    return escape(s, {'"': "&quot;"})


class Diagram:
    """One drawio page. Methods take an element id plus layout only; meaning comes from the dictionaries above."""

    def __init__(self):
        self.cells = []
        self.geo = {}

    def frame(self, cid, x, y, w, h):
        name, st = FRAMES[FRAME_IDS[cid]]
        style = ("rounded=1;arcSize=1;absoluteArcSize=1;html=1;whiteSpace=wrap;strokeWidth=1.5;verticalAlign=top;align=left;"
                 "spacingLeft=10;spacingRight=10;spacingTop=2;" + st + ";fontFamily=" + FONT)
        self._vertex(cid, name, style, x, y, w, h)

    def icon(self, cid, x, y, pos="bottom"):
        lab, st, w, h = NODES[cid]
        style = st + ";aspect=fixed;html=1;labelBackgroundColor=none;" + LABEL_POS[pos] + ";fontSize=17;fontColor=#1A1A1A;fontFamily=" + FONT
        self._vertex(cid, lab, style, x, y, w, h)

    def box(self, cid, x, y):
        label, w, h = BOXES[cid]
        style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF4CE;strokeColor=#C19C00;strokeWidth=1.5;fontSize=17;fontColor=#1A1A1A;fontFamily=" + FONT
        self._vertex(cid, label, style, x, y, w, h)

    def text(self, cid, label, x, y, w, h, size=17, bold=False, align="left"):
        style = ("text;html=1;whiteSpace=nowrap;align=%s;verticalAlign=middle;fontSize=%d;fontColor=#1A1A1A;fontStyle=%d;"
                 "labelBackgroundColor=none;spacing=0;fontFamily=%s") % (align, size, 1 if bold else 0, FONT)
        self._vertex(cid, label, style, x, y, w, h)

    def legend_text(self, cid, x, y, w, h, key=None):
        self.text(cid, LEGEND[key or cid], x, y, w, h)

    def _vertex(self, cid, label, style, x, y, w, h):
        self.geo[cid] = (x, y, w, h)
        self.cells.append('<mxCell id="%s" value="%s" style="%s" vertex="1" parent="1"><mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry"/></mxCell>'
                          % (cid, _q(label), style, x, y, w, h))

    def sample(self, cid, x1, y, x2, kind):
        """Legend sample line (no source/target)."""
        style = self._edge_style(kind)
        self.cells.append('<mxCell id="%s" value="" style="%s" edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
                          '<mxPoint x="%s" y="%s" as="sourcePoint"/><mxPoint x="%s" y="%s" as="targetPoint"/></mxGeometry></mxCell>'
                          % (cid, style, x1, y, x2, y))

    @staticmethod
    def _edge_style(kind):
        if kind == "main":
            return "strokeColor=%s;strokeWidth=3;endArrow=block;endFill=1;endSize=7;html=1;" % BLUE
        if kind == "link":
            return "strokeColor=%s;strokeWidth=1.5;dashed=1;dashPattern=4 4;endArrow=none;html=1;" % GREY
        return "strokeColor=%s;strokeWidth=1.8;endArrow=block;endFill=1;endSize=6;html=1;" % GREY

    def edge(self, cid, pts, at=None):
        """pts: absolute polyline [start on source boundary, waypoints..., end on target boundary].
        at: label centre on the path (required when the edge has a label)."""
        src, tgt, kind, label, tech, c4 = EDGES[cid]
        sx, sy, sw, sh = self.geo[src]
        tx, ty, tw, th = self.geo[tgt]
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        ex, ey = round((x0 - sx) / sw, 4), round((y0 - sy) / sh, 4)
        nx, ny = round((x1 - tx) / tw, 4), round((y1 - ty) / th, 4)
        for v in (ex, ey, nx, ny):
            assert -0.001 <= v <= 1.001, (cid, ex, ey, nx, ny)
        style = self._edge_style(kind) + ("rounded=0;edgeStyle=none;jumpStyle=arc;jumpSize=10;"
                                          "exitX=%s;exitY=%s;exitDx=0;exitDy=0;exitPerimeter=0;"
                                          "entryX=%s;entryY=%s;entryDx=0;entryDy=0;entryPerimeter=0;" % (ex, ey, nx, ny))
        gx = 0
        if label:
            color = BLUE if kind == "main" else "#1A1A1A"
            style += ("fontSize=%d;fontColor=%s;fontStyle=%d;labelBackgroundColor=#FFFFFF;fontFamily=%s;"
                      % (C4_PURPOSE_PX if c4 else 17, color, 1 if kind == "main" else 0, FONT))
            if c4 and tech:
                label = label + '<br><span style="font-size:%dpx;font-weight:normal">[%s]</span>' % (C4_TECH_PX, tech)
            gx = self._frac(pts, at) * 2 - 1
        wp = "".join('<mxPoint x="%s" y="%s"/>' % p for p in pts[1:-1])
        arr = '<Array as="points">%s</Array>' % wp if wp else ""
        self.cells.append('<mxCell id="%s" value="%s" style="%s" edge="1" parent="1" source="%s" target="%s">'
                          '<mxGeometry x="%s" relative="1" as="geometry">%s</mxGeometry></mxCell>'
                          % (cid, _q(label), style, src, tgt, round(gx, 4), arr))

    @staticmethod
    def _frac(pts, at):
        seg = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        total = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in seg)
        acc = 0
        for a, b in seg:
            L = abs(b[0] - a[0]) + abs(b[1] - a[1])
            on_h = a[1] == b[1] == at[1] and min(a[0], b[0]) <= at[0] <= max(a[0], b[0])
            on_v = a[0] == b[0] == at[0] and min(a[1], b[1]) <= at[1] <= max(a[1], b[1])
            if on_h or on_v:
                return (acc + abs(at[0] - a[0]) + abs(at[1] - a[1])) / total
            acc += L
        raise ValueError("label point %s not on path %s" % (at, pts))

    def xml(self, page_name):
        body = "".join(self.cells)
        return ('<mxfile host="drawio" agent="claude-opus"><diagram id="arch" name="%s"><mxGraphModel dx="1400" dy="1100" grid="0" gridSize="10" '
                'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1400" pageHeight="1130" '
                'background="#FFFFFF" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>%s</root></mxGraphModel></diagram></mxfile>\n'
                % (page_name, body))
