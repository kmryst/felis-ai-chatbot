"""Generate the felis-ai-chatbot architecture diagrams (drawio XML).

- full():         the full diagram (verification master)       -> docs/architecture/src/architecture.drawio
- request_flow(): diagram 1, the chat request flow (README)     -> docs/architecture/architecture-request-flow.drawio
- operations():   diagram 2, deployment / operations / monitoring / backup (README)
                                                                -> docs/architecture/architecture-operations.drawio

Each function holds layout only: coordinates, label side, edge waypoints and label position.
Labels, icons, edge endpoints, line types and [technology] come from elements.py.

usage: python3 gen.py            # write to the paths above
       python3 gen.py <out dir>  # write all three files into <out dir> (for comparison)
"""
import os
import sys

from elements import Diagram


def request_flow():
    d = Diagram()
    d.frame("entraId", 20, 60, 280, 175)
    d.frame("rgOpenai", 1170, 60, 220, 175)
    d.frame("rgMain", 340, 255, 1050, 560)
    d.frame("vnet", 360, 290, 1020, 335)
    d.frame("subnetApps", 375, 325, 620, 288)
    d.frame("caEnv", 390, 357, 590, 243)
    d.frame("subnetDb", 1010, 325, 355, 288)
    d.frame("legend", 20, 590, 300, 225)
    d.icon("entraIcon", 55, 105)
    d.icon("appRegistration", 195, 105)
    d.icon("browser", 20, 420)
    d.icon("openai", 1185, 100, pos="right")
    d.box("builtinAuth", 410, 420)
    d.icon("frontend", 612, 440)
    d.icon("backend", 850, 440)
    d.icon("postgres", 1236, 440)
    d.icon("identity", 400, 700, pos="right")
    d.icon("keyVault", 761, 700, pos="right")
    d.icon("privateDns", 1152, 700)
    d.edge("flow1", [(100, 422), (410, 422)], (220, 422))
    d.edge("flow2", [(90, 420), (90, 235)], (90, 328))
    d.edge("flow3", [(100, 482), (410, 482)], (220, 482))
    d.edge("authToFront", [(550, 473), (612, 473)])
    d.edge("flow4", [(680, 473), (850, 473)], (765, 473))
    d.edge("flow5", [(862, 440), (862, 104), (1185, 104)], (1040, 104))
    d.edge("flow6", [(918, 473), (1236, 473)], (1123, 473))
    d.edge("flow7", [(905, 440), (905, 164), (1185, 164)], (1050, 164))
    d.edge("token", [(520, 357), (520, 150), (300, 150)], (520, 200))
    d.edge("kvRefs", [(795, 600), (795, 700)], (795, 662))
    d.edge("vnetLink", [(1184, 700), (1184, 625)])
    d.sample("lgMain", 35, 645, 90, "main")
    d.legend_text("lgMainText", 100, 622, 210, 46)
    d.sample("lgOther", 35, 695, 90, "other")
    d.legend_text("lgOtherText", 100, 683, 210, 24)
    d.sample("lgLink", 35, 735, 90, "link")
    d.legend_text("lgLinkText", 100, 723, 210, 24)
    d.legend_text("lgNote", 35, 760, 280, 46)
    d.text("title", "felis-ai-chatbot Azure 構成図 ①：チャットのリクエストの流れ", 20, 10, 1300, 40, size=26, bold=True)
    return d.xml("① チャットのリクエストの流れ")


def operations():
    d = Diagram()
    d.frame("legend", 320, 60, 360, 90)
    d.frame("rgOpenai", 700, 60, 300, 190)
    d.frame("rgMain", 320, 280, 1070, 820)
    d.frame("vnet", 340, 320, 730, 560)
    d.frame("caEnv", 355, 360, 445, 505)
    d.frame("rgState", 20, 990, 260, 130)
    # nodes
    d.icon("github", 122, 100)
    d.icon("developer", 130, 573, pos="top")
    d.icon("resourceManager", 56, 830)
    d.icon("stateStorage", 138, 1025)
    d.icon("openai", 726, 110, pos="right")
    d.icon("backupStorage", 1250, 100, pos="left")
    d.icon("frontend", 410, 400)
    d.icon("backend", 620, 400)
    d.icon("jobs", 410, 552)
    d.icon("opsApp", 410, 720)
    d.icon("postgres", 880, 576, pos="top")
    d.icon("metricAlerts", 1110, 587, pos="right")
    d.icon("actionGroup", 1110, 720, pos="right")
    d.icon("logAlert", 1110, 830, pos="right")
    d.icon("logAnalytics", 1110, 960, pos="right")
    d.icon("keyVault", 880, 958, pos="top")
    d.icon("registry", 431, 930)
    # connections (communication direction)
    d.edge("probe", [(178, 128), (292, 128), (292, 433), (410, 433)], (235, 128))
    d.edge("probeForward", [(478, 433), (620, 433)], (549, 433))
    d.edge("jobStart", [(210, 585), (410, 585)], (262, 585))
    d.edge("exec", [(210, 613), (300, 613), (300, 753), (410, 753)], (380, 753))
    d.edge("push", [(210, 641), (270, 641), (270, 960), (431, 960)], (378, 960))
    d.edge("apply", [(130, 600), (80, 600), (80, 830)], (80, 700))
    d.edge("state", [(170, 653), (170, 1025)], (170, 780))
    d.edge("pull", [(465, 865), (465, 930)], (465, 905))
    d.edge("embedJob", [(478, 562), (760, 562), (760, 178)], (760, 300))
    d.edge("jobsDb", [(478, 608), (880, 608)], (650, 608))
    d.edge("opsDb", [(478, 753), (904, 753), (904, 640)], (640, 753))
    d.edge("backup", [(928, 582), (1090, 582), (1090, 230), (1280, 230), (1280, 158)], (1180, 230))
    d.edge("metricEval", [(1110, 627), (928, 627)], (995, 627))
    d.edge("notify1", [(1140, 643), (1140, 720)], (1140, 681))
    d.edge("notify2", [(1140, 830), (1140, 756)], (1140, 793))
    d.edge("kql", [(1142, 886), (1142, 960)], (1142, 923))
    d.edge("diag", [(948, 992), (1110, 992)], (1029, 992))
    d.edge("logs", [(720, 865), (720, 1060), (1142, 1060), (1142, 1024)], (930, 1060))
    # legend: line type + direction note only
    d.sample("lgOther", 335, 110, 390, "other")
    d.legend_text("lgOtherText", 400, 98, 270, 24, key="lgOtherOnly")
    d.text("title", "felis-ai-chatbot Azure 構成図 ②：デプロイ・運用・監視・バックアップ", 20, 10, 1300, 40, size=26, bold=True)
    return d.xml("② デプロイ・運用・監視・バックアップ")


def full():
    """Full diagram (verification master): union of the request-flow and operations diagrams."""
    d = Diagram()
    d.frame("entraId", 20, 60, 280, 175)
    d.frame("rgOpenai", 1480, 60, 230, 175)
    d.frame("rgMain", 340, 255, 1600, 935)
    d.frame("vnet", 360, 290, 1150, 650)
    d.frame("subnetApps", 375, 325, 640, 600)
    d.frame("caEnv", 390, 357, 610, 553)
    d.frame("subnetDb", 1030, 325, 465, 600)
    d.frame("rgState", 20, 1080, 260, 130)
    d.frame("legend", 20, 1230, 300, 225)
    # nodes
    d.icon("entraIcon", 55, 105)
    d.icon("appRegistration", 195, 105)
    d.icon("browser", 20, 420)
    d.icon("openai", 1500, 100, pos="right")
    d.icon("backupStorage", 1750, 100, pos="right")
    d.box("builtinAuth", 430, 420)
    d.icon("frontend", 644, 440)
    d.icon("backend", 870, 440)
    d.icon("opsApp", 612, 600)
    d.icon("jobs", 612, 747)
    d.icon("postgres", 1260, 450, pos="top")
    d.icon("registry", 400, 990)
    d.icon("identity", 640, 990)
    d.icon("keyVault", 900, 1000, pos="right")
    d.icon("privateDns", 1350, 990)
    d.icon("metricAlerts", 1560, 488, pos="right")
    d.icon("actionGroup", 1560, 620, pos="right")
    d.icon("logAlert", 1560, 730, pos="right")
    d.icon("logAnalytics", 1560, 870, pos="right")
    d.icon("github", 110, 560)
    d.icon("developer", 130, 740, pos="top")
    d.icon("resourceManager", 56, 950)
    d.icon("stateStorage", 138, 1120)
    # numbered request flow
    d.edge("flow1", [(100, 422), (430, 422)], (220, 422))
    d.edge("flow2", [(90, 420), (90, 235)], (90, 328))
    d.edge("flow3", [(100, 482), (430, 482)], (220, 482))
    d.edge("authToFront", [(570, 473), (644, 473)])
    d.edge("flow4", [(712, 448), (870, 448)], (791, 448))
    d.edge("flow5", [(882, 440), (882, 104), (1500, 104)], (1180, 104))
    d.edge("flow6", [(938, 483), (1260, 483)], (1145, 483))
    d.edge("flow7", [(925, 440), (925, 164), (1500, 164)], (1180, 164))
    d.edge("token", [(520, 357), (520, 150), (300, 150)], (520, 200))
    d.edge("kvRefs", [(934, 910), (934, 1000)], (934, 970))
    d.edge("vnetLink", [(1382, 990), (1382, 940)])
    # deployment, operations, monitoring, backup
    d.edge("probe", [(166, 588), (585, 588), (585, 500), (644, 500)], (250, 588))
    d.edge("probeForward", [(712, 490), (870, 490)], (791, 490))
    d.edge("exec", [(210, 755), (320, 755), (320, 633), (612, 633)], (500, 633))
    d.edge("jobStart", [(210, 780), (612, 780)], (500, 780))
    d.edge("push", [(210, 808), (270, 808), (270, 1023), (400, 1023)], (270, 900))
    d.edge("apply", [(130, 780), (80, 780), (80, 950)], (80, 870))
    d.edge("state", [(170, 820), (170, 1120)], (170, 960))
    d.edge("pull", [(434, 910), (434, 990)], (434, 965))
    d.edge("jobsDb", [(680, 760), (1300, 760), (1300, 514)], (790, 760))
    d.edge("embedJob", [(680, 808), (1534, 808), (1534, 168)], (1160, 808))
    d.edge("opsDb", [(680, 633), (1268, 633), (1268, 514)], (760, 633))
    d.edge("backup", [(1308, 465), (1780, 465), (1780, 158)], (1780, 360))
    d.edge("metricEval", [(1560, 505), (1308, 505)], (1400, 505))
    d.edge("notify1", [(1590, 544), (1590, 620)], (1590, 582))
    d.edge("notify2", [(1590, 730), (1590, 656)], (1590, 693))
    d.edge("kql", [(1592, 786), (1592, 870)], (1592, 828))
    d.edge("diag", [(934, 1068), (934, 1110), (1535, 1110), (1535, 925), (1560, 925)], (1230, 1110))
    d.edge("logs", [(1000, 900), (1560, 900)], (1300, 900))
    # legend: line types + direction note only
    d.sample("lgMain", 35, 1285, 90, "main")
    d.legend_text("lgMainText", 100, 1262, 210, 46)
    d.sample("lgOther", 35, 1335, 90, "other")
    d.legend_text("lgOtherText", 100, 1323, 210, 24)
    d.sample("lgLink", 35, 1375, 90, "link")
    d.legend_text("lgLinkText", 100, 1363, 210, 24)
    d.legend_text("lgNote", 35, 1400, 280, 46)
    d.text("title", "felis-ai-chatbot Azure 構成図（全体）", 20, 10, 1300, 40, size=26, bold=True)
    return d.xml("全体図")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) > 1:
        out = sys.argv[1]
        targets = {
            "architecture.drawio": os.path.join(out, "architecture.drawio"),
            "request-flow": os.path.join(out, "architecture-request-flow.drawio"),
            "operations": os.path.join(out, "architecture-operations.drawio"),
        }
    else:
        targets = {
            "architecture.drawio": os.path.join(here, "architecture.drawio"),
            "request-flow": os.path.join(here, "..", "architecture-request-flow.drawio"),
            "operations": os.path.join(here, "..", "architecture-operations.drawio"),
        }
    for key, fn in (("architecture.drawio", full), ("request-flow", request_flow), ("operations", operations)):
        with open(targets[key], "w", encoding="utf-8") as f:
            f.write(fn())


if __name__ == "__main__":
    main()
