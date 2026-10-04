#!/usr/bin/env python3
"""Fill the next 7 days of morning (term) + night (career/link) content.

Runs in GitHub Actions. For each of the next 7 JST dates that has no content
yet, generates via the Anthropic API and renders the card image:
  morning: 【用語解説】term post  + blue diagram card
  night  : career message post    + green message card
           (Mon/Thu: Udemy講座の紹介 / Tue/Fri: InfraGym promo + fixed banner)

Only fills gaps (never overwrites an existing queue/posted file), so it is safe
to run daily as a self-healing backfill as well as weekly.

Env: ANTHROPIC_API_KEY (required).
"""
import datetime
import difflib
import glob
import json
import os
import re
import subprocess
import sys
import urllib.request

MODEL = "claude-sonnet-4-5"
JST = datetime.timezone(datetime.timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Tue/Fri night = InfraGym promo (free gamified CCNA training app).
INFRAGYM_URL = "https://lp.theit.co.jp/p/DbzLM6ruxTc8?ftid=G9bN143EI7nd"
INFRAGYM_BANNER = os.path.join(ROOT, "assets", "infragym_banner.png")

# Evening (18:00) = daily RackShare promo (infra-engineer knowledge-sharing site).
RACKSHARE_URL = "https://rackshare.jp/"

# Afternoon (15:00) = daily whoami 年収診断 promo. Text only so X shows the site's
# OGP link-card (whole card is tappable -> better click-through than an image).
# UTM param marks the traffic as coming from X.
WHOAMI_URL = "https://www.whoami-jobs.com/shindan/?utm_source=x&utm_medium=social"
WHOAMI_ANGLES = [
    "衝撃の事実で止める: 同じ30歳のインフラエンジニアでも、担当工程だけで年収が125万円ちがう。あなたはどちら側か?",
    "期待×好奇心: あなたの『適正年収』は、今もらっている額より高いかもしれない。市場での本当の値段を確かめる",
    "損失回避: 相場を知らないまま働き続けると、年間で数十万円損しているかもしれない。まず今の市場価値を知る",
    "頭打ちの危機感: 運用監視のままだと年収は頭打ちになりやすい。設計・構築側とどれだけ差がつくかは診断で具体的に分かる、という好奇心",
    "低リスクの誘い: 転職しなくていい。いまの自分の市場価値(想定年収)だけ、こっそり確かめてみる",
    "自分ごと化×手軽さ: 8問60秒で『あなたの数字』が出る。年齢・工程・資格から、いま転職したらの想定年収を算出",
]

# Mon/Thu night = Udemy講座の紹介(テキストのみ。XがUdemyのリンクカードを表示する)。
# Kindle(Amazon)のCCNP問題集の宣伝は2026-10-04で終了。
# 5講座を月・木の順番で1本ずつローテーション(同じ講座が連続しない)。
UDEMY_COURSES = [
    {
        "key": "ccna",
        "url": "https://www.udemy.com/course/ccna-200-301-practice-exam-jp/?referralCode=1001F8F2239359150115",
        "title": "合格者1,000名超の講師が作成！CCNA 200-301【v1.1対応】本番形式の模擬試験問題集 6回・600問",
        "facts": "CCNA 200-301(v1.1)対応。120分・100問の模試6回(全600問)で全6分野を網羅。正解の理由だけでなく、間違いの選択肢がなぜ違うかまで全問解説。対象: 参考書やWeb問題集を解き終えて別の問題で実力を確かめたい人、試験直前に弱点分野を洗い出したい人。",
        "tags": "#CCNA",
    },
    {
        "key": "encor",
        "url": "https://www.udemy.com/course/ccnp-encor-350-401-practice-exam-jp/?referralCode=A21B0AEB3D8447F883CB",
        "title": "【2026最新・v1.2対応】合格者1,000名超の講師が作成！CCNP ENCOR 350-401 模試6回・600問",
        "facts": "CCNP ENCOR 350-401(v1.2)対応。120分・100問の模試6回(全600問)。対象: 参考書や動画講座を終えて本番形式で実力を確認したい人、試験直前に弱点分野を特定して仕上げたい人。",
        "tags": "#CCNP #ENCOR",
    },
    {
        "key": "nwdesign",
        "url": "https://www.udemy.com/course/network-design-document/?referralCode=8D4D33119B37DA2CF20A",
        "title": "【Word・Excelテンプレート付】ネットワーク基本設計書の書き方｜設計書が書けるようになる実務入門",
        "facts": "ネットワークの基本設計書を39分(全25講義)で最後まで。論理設計・物理設計・非機能設計の書き方を、1つの実案件を題材に学ぶ。論理構成図とセグメント一覧の対応、アドレス・VLANの割り当て方針、ポート収容の決め方、可用性・セキュリティ・運用保守設計。Word形式の基本設計書テンプレートとExcelテンプレート3点(セグメント一覧・ポート収容表・通信要件表)付き。対象: 運用・監視から設計構築へ進みたい人、設計書を書いたことがない人。",
        "tags": "#ネットワークエンジニア",
    },
    {
        "key": "cissp1",
        "url": "https://www.udemy.com/course/cissp-domain1/?referralCode=63FDA90AD0C2EB5947FC",
        "title": "【日本人講師が教える】ゼロからわかるCISSP講座 ドメイン1：セキュリティとリスクマネジメント",
        "facts": "CISSPドメイン1だけを46レクチャー・約2時間で完走。翻訳ではない日本語オリジナルの解説。本番形式の演習43問で『4つとも正しく見える』問題の選び方まで身につける。内容: CIA・真正性・否認防止、リスク/脅威/脆弱性の関係、ポリシー・標準・手順・ガイドラインの違い、法令・コンプライアンス・倫理、事業継続とガバナンス。対象: CISSPの学習をはじめる人、参考書が難しいと感じている人。",
        "tags": "#CISSP",
    },
    {
        "key": "enarsi",
        "url": "https://www.udemy.com/course/ccnp-enarsi-300-410-practice-exam-jp/?referralCode=390B0E96280FF06EA7FF",
        "title": "【2026最新・v1.1対応】合格者1,000名超の講師が作成！CCNP ENARSI 300-410 模試6回600問",
        "facts": "CCNP ENARSI 300-410(v1.1)対応。本番と同じペースの100問模試6回(全600問)でv1.1の全4分野を網羅。設定・show出力・debugを読む問題が中心で、全選択肢を解説。対象: 参考書や動画講座を終えて本番形式で実力を確認したい人、試験直前に弱点分野を洗い出したい人。",
        "tags": "#CCNP #ENARSI",
    },
]
UDEMY_ANGLES = [
    "受講者の悩み(つまずきポイント)への共感から入り、この講座で何ができるようになるかを具体的に示す",
    "この講座の中身を具体的な数字(問題数・時間・レクチャー数・テンプレート数など、事実のみ)で端的に伝える",
    "『こんな人に向いている』を明確にして、該当する人に届くように書く",
]


def udemy_course_for(d):
    """Mon/Thu の何回目かで講座を決める(月・木で1本ずつ順番に進む)。"""
    week = (d.toordinal() - 1) // 7  # Monday-based week number
    n = week * 2 + (1 if d.weekday() == 3 else 0)
    return UDEMY_COURSES[n % len(UDEMY_COURSES)], UDEMY_ANGLES[(n // len(UDEMY_COURSES)) % len(UDEMY_ANGLES)]


# NESPE campaign: during this window the night slot becomes a campaign post
# driving to the LP (replacing the usual career / LINE-CCNA nights).
CAMPAIGN_END = datetime.date(2026, 8, 27)
LP_URL = "https://lp.theit.co.jp/p/8bJgbvOT0crt?ftid=fnnF6ycboBC4"


def wlen(text):
    """X weighted length: JP/full-width = 2, ASCII = 1, each URL counts as 23."""
    t = re.sub(r"https?://\S+", "x" * 23, text)
    n = 0
    for ch in t:
        n += 1 if ord(ch) < 0x100 else 2
    return n


def anthropic(api_key, prompt, max_tokens=1500):
    body = {"model": MODEL, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL) or re.search(r"(\{.*\})", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON in output: " + text[:400])
    # strict=False tolerates raw newlines/tabs the model sometimes emits
    # inside JSON string values (e.g. the multi-line "post" field).
    return json.loads(m.group(1), strict=False)


# 朝の用語は「AIに選ばせない」。このリストから未使用のものを順番に使う
# (AIに既出リストを渡しても同じ用語(CDP)を選び続けたため)。
TERM_POOL = [
    "ポートセキュリティ", "DHCPスヌーピング", "DAI", "IPv6", "リンクローカルアドレス", "SLAAC",
    "EUI-64", "NDP", "APIPA", "CIDR", "VLSM", "ルート集約", "アドミニストレーティブディスタンス",
    "メトリック", "ロンゲストマッチ", "フローティングスタティックルート", "デフォルトルート",
    "ネイティブVLAN", "ボイスVLAN", "PortFast", "BPDUガード", "ルートガード", "RSTP", "MSTP",
    "コリジョンドメイン", "ブロードキャストドメイン", "全二重と半二重", "オートネゴシエーション",
    "MACアドレステーブル", "ARPテーブル", "TTL", "3ウェイハンドシェイク", "ウィンドウサイズ",
    "PAT", "スタティックNAT", "内部ローカルアドレス", "NTP", "SSH", "AAA", "TACACS+",
    "802.1X", "WPA3", "SSID", "WLC", "CAPWAP", "チャネルボンディング", "2.4GHzと5GHz",
    "OSPFエリア", "DR/BDR", "ルーターID", "LSA", "SPF", "ハローパケット", "デッドインターバル",
    "標準ACLと拡張ACL", "ワイルドカードマスク", "暗黙のdeny", "ステートフルファイアウォール",
    "IPS", "VPN", "IPsec", "GRE", "SD-WAN", "SDN", "コントロールプレーン", "データプレーン",
    "REST API", "JSON", "Ansible", "NETCONF", "Cisco DNA Center", "仮想化", "コンテナ",
    "クラウドの3つのサービスモデル", "PoE+", "光ファイバー(シングルモードとマルチモード)",
    "UTPケーブル", "ストレートとクロス", "Auto-MDIX", "ループバックインターフェイス",
    "サブインターフェイス", "ルーターオンアスティック", "レイヤ3スイッチ", "CEF", "MTUとMSS",
    "フラグメンテーション", "traceroute", "ping", "show ip interface brief", "running-configとstartup-config",
    "コンフィグレジスタ", "IOSのモード", "enable secret", "バナー(MOTD)", "CDPとLLDPの違い",
]


def _norm(t):
    return re.sub(r"[\s　()（）/・\-]", "", t or "").upper()


def pick_term(avoid):
    used = {_norm(t) for t in avoid}
    for t in TERM_POOL:
        if _norm(t) not in used:
            return t
    return None


def _first_line(path):
    try:
        return open(path, encoding="utf-8").read().strip()
    except OSError:
        return ""


def recent_texts(slot, days=21):
    """Texts already posted/queued for a slot (newest first)."""
    files = sorted(glob.glob(os.path.join(ROOT, "posted", f"*-{slot}.txt"))
                   + glob.glob(os.path.join(ROOT, "queue", f"*-{slot}.txt")), reverse=True)
    return [_first_line(f) for f in files[: days * 2]]


def too_similar(text, others, th=0.55):
    head = text[:120]
    return any(difflib.SequenceMatcher(None, head, o[:120]).ratio() >= th for o in others if o)


def purge_duplicates(today):
    """Delete future queue files that repeat an already-used topic so they get regenerated."""
    removed = []
    seen_terms = set()
    for p in sorted(glob.glob(os.path.join(ROOT, "posted", "*-morning.txt"))):
        mm = re.search(r"【用語解説】(.+?)とは", _first_line(p))
        if mm:
            seen_terms.add(_norm(mm.group(1)))
    for p in sorted(glob.glob(os.path.join(ROOT, "queue", "*-morning.txt"))):
        date = os.path.basename(p)[:10]
        if date < today.isoformat():
            continue
        mm = re.search(r"【用語解説】(.+?)とは", _first_line(p))
        key = _norm(mm.group(1)) if mm else ""
        if key and key in seen_terms:
            os.remove(p)
            png = p.replace(".txt", ".png")
            if os.path.exists(png):
                os.remove(png)
            removed.append(os.path.basename(p))
        elif key:
            seen_terms.add(key)
    for slot in ("afternoon", "evening", "night"):
        prior = [_first_line(p) for p in sorted(glob.glob(os.path.join(ROOT, "posted", f"*-{slot}.txt")))[-14:]]
        for p in sorted(glob.glob(os.path.join(ROOT, "queue", f"*-{slot}.txt"))):
            if os.path.basename(p)[:10] < today.isoformat():
                continue
            t = _first_line(p)
            # CCNP/InfraGym nights are fixed-format promos; only compare career-type nights
            if slot == "night" and ("udemy.com" in t or "lp.theit.co.jp" in t):
                continue
            if too_similar(t, prior[-5:]):
                os.remove(p)
                png = p.replace(".txt", ".png")
                if os.path.exists(png):
                    os.remove(png)
                removed.append(os.path.basename(p))
            else:
                prior.append(t)
    return removed


def used_terms():
    terms = set()
    for d in ("queue", "posted"):
        for p in glob.glob(os.path.join(ROOT, d, "*-morning.txt")):
            try:
                first = open(p, encoding="utf-8").readline()
            except OSError:
                continue
            mm = re.search(r"【用語解説】(.+?)とは", first)
            if mm:
                terms.add(mm.group(1).strip())
    return terms


def render(script, spec, out_png):
    """Render a card; on failure (e.g. bad SVG) retry with diagram removed."""
    spec_path = out_png.replace(".png", ".spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "card", script), spec_path, out_png], check=True)
    except subprocess.CalledProcessError:
        spec.pop("diagram", None)
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False)
        subprocess.run([sys.executable, os.path.join(ROOT, "card", script), spec_path, out_png], check=True)
    os.remove(spec_path)


def gen_morning(api_key, avoid):
    term = pick_term(avoid)
    if term:
        topic = f"今回解説する用語は必ず「{term}」。別の用語に変えてはいけない。"
    else:
        topic = f"CCNA/ネットワークの重要用語を1つ選ぶ。次の既出用語は絶対に使わない: {', '.join(sorted(avoid))}"
    prompt = f"""あなたはX「ネスペ社長」(@nespe_shacho、CCNA/ネットワーク教育)の朝の投稿を作ります。CCNA/ネットワークの用語を1つ、初学者向けに解説してください。{topic}

次のJSONだけを```json ... ```で出力:
{{
 "term": "英略語などの用語名(例: ARP)",
 "sub": "正式名称/和名(例: Address Resolution Protocol)",
 "term_size": 110,  // 用語が長い場合(日本語など)は72程度に
 "desc": "初学者向け解説。<b>語句</b>で水色強調可。全角60字程度。",
 "diagram": "その用語の仕組みが一目で分かる簡潔なSVG。viewBox=\\"0 0 1072 300\\"。濃紺背景に映える配色(白=#fff, 水色=#38bdf8/#7dd3fc, 緑=#4ade80, 黄=#fbbf24)。角丸rect+矢印+textで構成。文字はfont-size 24〜30, font-weight 700。日本語可。壊れたSVGは不可、必ず妥当なSVG。",
 "post": "【用語解説】<term>とは\\n<解説文2〜3文>\\n\\n#CCNA という形の投稿本文。日本語全角=2/半角=1で270単位以内。URLは入れない。末尾のハッシュタグは #CCNA だけ(他のタグは絶対に付けない)。"
}}"""
    return anthropic(api_key, prompt, max_tokens=2000)


CAREER_THEMES = [
    "勉強時間の作り方(働きながら)", "資格の価値と限界", "現場で評価される人の共通点", "障害対応で学んだこと",
    "設計・構築へのステップアップ", "上司・先輩への質問・報連相のコツ", "転職のタイミングの見極め",
    "手順書・ドキュメントを書く力", "英語ドキュメントとの付き合い方", "クラウド時代のネットワークエンジニア",
    "運用監視から抜け出す方法", "検証環境(Packet Tracer/実機)で手を動かす価値", "30代からの学び直し",
    "面接で実務経験をどう話すか",
]


def gen_career(api_key, theme, recent):
    avoid = "\n".join("- " + r.splitlines()[0][:60] for r in recent[:10] if r)
    prompt = """あなたはX「ネスペ社長」(@nespe_shacho、株式会社iT代表・元インフラエンジニア、CCNA教育)の夜の投稿を作ります。元インフラエンジニア社長の目線で前向きに1つ。
今回のテーマ(必ずこれで書く): """ + theme + """
直近の投稿と書き出し・主張が被らないこと(「実務1年目」「未経験の1年目」で始めるのは禁止)。直近の投稿:
""" + avoid + """

次のJSONだけを```json ... ```で出力:
{
 "badge": "キャリア",
 "headline": "投稿の核となる一言を引用調で。<span class=\\"hi\\">語句</span>で緑強調可。<br>で改行可。全角30字程度。",
 "head_size": 50,  // 長い場合は42〜46
 "body": "補足1〜2文。",
 "post": "夜の投稿本文。上記の核を含め具体的で前向きに。文末に空行を挟んで読者が返信したくなる短い問いかけを1文。日本語全角=2/半角=1で270単位以内。URLは入れない。"
}"""
    return anthropic(api_key, prompt, max_tokens=1500)


def gen_infragym(api_key, pattern):
    style = (
        "『参考書だけだと丸暗記で心が折れがち』という挫折ポイントの共感から、"
        "『手を動かして・ゲーム感覚で(レベルや称号)続けられる無料アプリ InfraGym を使ってみて』と自然に誘導"
        if pattern == "pain" else
        "『毎日たった5分、指を動かすだけでCCNAがサクサク進む』という切り口で、"
        "レベル・称号・模試つきのゲーム感覚の無料アプリ InfraGym を軽やかに紹介"
    )
    prompt = f"""あなたはX「ネスペ社長」(@nespe_shacho、株式会社iT代表・CCNA教育)の夜の投稿を作ります。
無料のCCNA学習アプリ「InfraGym(インフラジム)」への誘導投稿を1つ。
アプリの事実: CCNA 200-301を「手を動かして」攻略する無料トレーニングアプリ。1日5分、図解＋クイズ。レベル・XP・称号・実績バッジでゲーム感覚に続けられる。CCNA全1091問・実力テスト(模試)つき。延べ1,000名を合格へ導いた現役講師が監修。登録なしですぐ始められスマホだけで完結。誇大表現(絶対合格・誰でも等)は禁止、事実ベースで誠実に。
今回の切り口: {style}。宣伝くさくなりすぎず、社長本人の一言として自然に。

次のJSONだけを```json ... ```で出力:
{{"post": "投稿本文。改行で {INFRAGYM_URL} を必ず1回含める。文末で『無料で試してみて』的に軽く促す。日本語全角=2/半角=1・URLは23として270単位以内。ハッシュタグは付けても #CCNA を1個だけ、無くてもよい。"}}"""
    s = anthropic(api_key, prompt, max_tokens=800)
    for _ in range(2):
        if wlen(s.get("post", "")) <= 270:
            break
        s = anthropic(
            api_key,
            prompt + f"\n\n【再指示】前回が長すぎました。{INFRAGYM_URL} を除いた地の文を削り、全体を250単位以内に必ず収めてください。",
            max_tokens=800,
        )
    return s


CAMPAIGN_ANGLES = [
    "IPAの制度改正で現行制度は2026年度で終了予定。『ネットワークスペシャリスト』という独立区分で受けられるのは今年が最後、という緊急性",
    "独学で一番の遠回りは『何から・どの順で』の迷い。まず学習ロードマップで解消できる、という切り口",
    "働きながらでも、実務経験が浅くても、正しい順番と教材があれば最短で狙える、という背中押し",
    "本番の必修講義(R7年度版・必修講義版)を14日間そのまま無料で体験できる、というオファーの中身",
    "積み上げたネットワークの知識を『国家資格』で証明すると、仕事や転職で活きる、という価値",
    "2026年度の試験スケジュール(申込10/6〜、科目A 10/17〜、科目B 11/11〜)を示し、今からでも約2ヶ月ある、という現実的な後押し",
    "『いつかネスペを』で止まっている人へ。まず14日間無料で、続けるかは後で決めればいい、というハードル下げ",
]


def gen_campaign(api_key, angle, extra=""):
    prompt = f"""あなたはX「ネスペ社長」(@nespe_shacho、株式会社iT代表)の夜の投稿を作ります。無料キャンペーンの告知を1つ。
オファー: 国家資格「ネットワークスペシャリスト(ネスペ)」の合格講座eラーニング(R7年度版・必修講義版)を14日間無料開放+学習ロードマップ。提供は株式会社iT。現行のネスペ試験制度は2026年度で終了予定で、独立区分で受けられるのは今年が最後。誇大表現(絶対合格・誰でも等)は禁止。事実に基づき誠実に。
今回の切り口: {angle}

【本文の絶対条件】とても短くまとめる。構成は「①切り口の要点1文（40字以内）→ ②14日間無料を一言で（30字以内）→ 改行して {LP_URL} → ④短い一言CTA（例: 本文のリンクから今すぐ）」。CTAは必ず「本文のリンクから」等と言い、「プロフ(ィール)のリンクから」とは絶対に書かない(URLは本文内にあるため)。長い説明・複数段落は禁止。日本語全角=2/半角=1・URL=23として、全体で必ず250単位以内に収める(超えたら短くやり直す)。ハッシュタグは付けても #ネスペ を1個だけ、無くてもよい。{extra}

次のJSONだけを```json ... ```で出力:
{{
 "post": "上記条件を厳守した短い投稿本文。改行で {LP_URL} を必ず1回含める。",
 "badge": "カード上部の短いバッジ。例: 期間限定・14日間無料",
 "last": "見出し上の小さな一言。例: ＼ “ネスペ”として挑めるのは今年が最後 ／",
 "headline": "カードの主見出し。<span class=\\"y\\">語句</span>でゴールド強調可。全角24字程度。",
 "head_size": 54,  // 長い場合は 48
 "points": ["特典・魅力を短く2〜3個。<b>語句</b>で強調可。例: ネスペ講座を14日間 無料"],
 "cta_big": "本文のリンクから今すぐ無料で"
}}"""
    s = anthropic(api_key, prompt, max_tokens=1500)
    # Length guard: X limit is 280 weighted; regenerate shorter if needed.
    for _ in range(2):
        if wlen(s.get("post", "")) <= 270:
            break
        s = anthropic(
            api_key,
            prompt + f"\n\n【再指示】前回の本文が長すぎました。{LP_URL} を除いた地の文を大幅に削り、全体を230単位以内に必ず収めてください。",
            max_tokens=1500,
        )
    return s


RACKSHARE_ANGLES = [
    "インフラの仕事は外から見えにくく、止めなければ何もしていないように見える。成果物は顧客環境に紐づいて社外に出せず、実力を示す材料が資格名と経験年数しかない——だからこそ書いて残せば実績になる、という切り口",
    "現場で解決した知識が社内チャットや個人の頭の中に埋もれ、同じ問題を別の誰かがまた一から調べている。共有すれば誰かの調査時間を短くできる、という切り口",
    "個人ブログより見つけてもらいやすく、書いた記事がそのままポートフォリオになる。転職や案件で『資格では見えない実力』を示せる、という切り口",
    "障害対応・設定・検証結果のナレッジを残すと、知識が整理され自分の技術資産になる。得意分野でブランディングもできる、という切り口",
    "使い方は『読む・質問する・書く』の3つ。まずは読む・質問するだけでもいい。現場の疑問を解決する場所として使ってみて、という切り口",
    "『インフラのことなら、ここに行けばいい』——日本のインフラエンジニアが集まる場所を目指している。まだ最初のバージョンで、利用者の声を聞きながら育てている段階、という切り口",
]


def gen_rackshare(api_key, angle):
    prompt = f"""あなたはX「ネスペ社長」(@nespe_shacho、株式会社iT代表・元インフラエンジニア)の夕方の投稿を作ります。
インフラエンジニア向けの知識共有サイト「RackShare(ラックシェア)」への誘導投稿を1つ。
サイトの事実: 現場で得た知識を共有し、自分の実績として残せる場所。QiitaとYahoo!知恵袋のインフラエンジニア版。使い方は「読む・質問する・書く」の3つ。障害対応・設定・検証結果などのナレッジを投稿できる。無料ではじめられる。運営は株式会社iT。書けば知識が整理され技術資産になり、資格では見えない実力を示せてポートフォリオにもなる。誇大表現は禁止、事実ベースで誠実に。
文体: です・ます調(敬語)。一人称は「私」、読者は「あなた」。断定は弱めない。
今回の切り口: {angle}

【本文の絶対条件】短くまとめる。構成は「①切り口の要点を1〜2文(合計70字以内)→ 改行して {RACKSHARE_URL} → ③短い一言CTA(例: 無料ではじめられます)」。長い説明・3段落以上は禁止。日本語全角=2/半角=1・URL=23として、全体で必ず240単位以内に収める(超えたら短くやり直す)。ハッシュタグは付けても #インフラエンジニア を1個だけ、無くてもよい。

次のJSONだけを```json ... ```で出力:
{{
 "post": "上記条件を厳守した短い投稿本文。改行で {RACKSHARE_URL} を必ず1回含める。",
 "badge": "カード右上の短いバッジ。例: インフラの知識共有",
 "headline": "カードの主見出し。<span class=\\"c\\">語句</span>で水色、<span class=\\"y\\">語句</span>でゴールド強調可。全角22字程度。",
 "head_size": 54,
 "points": ["魅力を短く2〜3個。<b>語句</b>で強調可。例: 書けば<b>技術資産</b>になる"],
 "cta_big": "無料ではじめる"
}}"""
    s = anthropic(api_key, prompt, max_tokens=1200)
    for _ in range(2):
        if wlen(s.get("post", "")) <= 270:
            break
        s = anthropic(
            api_key,
            prompt + f"\n\n【再指示】前回が長すぎました。{RACKSHARE_URL} を除いた地の文を削り、全体を250単位以内に必ず収めてください。",
            max_tokens=1200,
        )
    return s


def gen_whoami(api_key, angle):
    prompt = f"""あなたはX「ネスペ社長」(@nespe_shacho、株式会社iT代表・元インフラエンジニア)の投稿を作ります。
無料の「whoami年収診断」への誘導投稿を1つ。
サービスの事実: ネットワーク・インフラエンジニア専用の年収診断。年齢・担当工程・企業規模・勤務地・クラウドスキル・資格の8問(約60秒)に答えると、いま転職した場合の想定年収を算出。根拠は厚労省の賃金構造基本統計調査＋dodaの約60万件の職種別×年代別データで、算出ロジックも公開。登録不要でその場で結果が出る。誇大表現は禁止、事実ベースで誠実に。
文体: です・ます調をベースにしつつ、SNSで指を止めさせる歯切れの良さを優先。一人称は「私」、読者は「あなた」。
今回の切り口: {angle}

【最優先の目的】クリック率(CTR)の最大化。リンク(年収診断ページ)をタップさせることが唯一のゴール。
【CTRを上げるための必須ルール】
- 1行目は「スクロールを止めるフック」にする。具体的な数字・意外な事実・あなたへの鋭い問いかけのいずれかで始め、抽象的な前置きは書かない。
- 続く1文で『クリックしないと自分の答えが分からない』好奇心の隙間(カーブ)を作る。結論を全部書かず、あなた自身の数字は診断でしか分からない、と引く。
- 読者を「あなた」で名指しし、自分ごと化させる。
- CTAは摩擦を徹底的に下げる: 「無料・登録不要・8問60秒」を必ず入れる。
- OGPリンクカードにタイトルと画像が出るので、本文でサービス名や説明を長々繰り返さない(重複は逆効果)。本文は"引き"に集中。
【事実の厳守(最重要・違反禁止)】具体的な金額として断定してよいのは、診断ページで公表されている事実『同じ30歳でも担当工程だけで年収が125万円ちがう』のみ。それ以外の年収差の具体額(例: 150万円/50万円 等)を事実として書かない。『何人も見てきた』『〜な人を見た』等の作り話の体験談・実績を書かない。工程や資格で年収に差が出ること自体は事実なので方向性として触れてよいが、未確認の数字は断定せず『いくら差がつくかは診断で分かる』という形で好奇心に変換する。誇大表現(必ず上がる等)も禁止。
【構成】①強フック1文 → ②好奇心を煽る1文 → 改行して {WHOAMI_URL} → ③摩擦ゼロの短いCTA。3段落以上・長い説明・箇条書きは禁止。
日本語全角=2/半角=1・URLは23として、全体で必ず240単位以内に収める(超えたら短くやり直す)。ハッシュタグは原則付けない(CTRを下げるため)。

次のJSONだけを```json ... ```で出力:
{{"post": "上記条件を厳守した短い投稿本文。改行で {WHOAMI_URL} を必ず1回含める。"}}"""
    s = anthropic(api_key, prompt, max_tokens=900)
    for _ in range(2):
        if wlen(s.get("post", "")) <= 270:
            break
        s = anthropic(api_key, prompt + f"\n\n【再指示】前回が長すぎました。{WHOAMI_URL} を除いた地の文を削り、全体を240単位以内に必ず収めてください。", max_tokens=900)
    return s


def gen_udemy(api_key, course, angle):
    url = course["url"]
    prompt = f"""あなたはX「ネスペ社長」(@nespe_shacho、株式会社iT代表・元インフラエンジニア、CCNA/CCNP/CISSP教育)の夜の投稿を作ります。
自分が作ったUdemy講座の紹介投稿を1つ。
講座名: {course['title']}
講座の事実: {course['facts']}
今回の切り口: {angle}

【ルール】
- 書いてよいのは上の事実だけ。受講者数・評価・セール価格・合格率・体験談など、書かれていない数字や話を作らない。誇大表現(絶対合格・誰でも・簡単に等)は禁止。
- 講師の実績(合格者1,000名超など)と講座の中身を、論理的につながらない形で結びつけない(例:「現場の経験から本番で問われる判断を問題にした」はNG)。実績に触れるなら講座名の事実として軽く触れる程度。
- 「再配布」という語は使わない(ルーティングのredistributionは「再配送」)。
- 文体: です・ます調。一人称は「私」。宣伝くさくしすぎず、講師本人の一言として自然に。
- 構成: ①読者が手を止める1文目 → ②講座で得られることを1〜2文 → 改行して {url} → ③短いCTA1文。箇条書きは使ってもよいが3行まで。
- URLは {url} をそのまま1回だけ入れる(紹介コードを消さない・書き換えない)。
- 日本語全角=2/半角=1・URLは23として、全体で必ず260単位以内。ハッシュタグは末尾に {course['tags']} のみ(他は付けない)。

次のJSONだけを```json ... ```で出力:
{{"post": "上記条件を厳守した投稿本文"}}"""
    s = anthropic(api_key, prompt, max_tokens=900)
    for _ in range(2):
        post = s.get("post", "")
        if wlen(post) <= 270 and url in post:
            break
        s = anthropic(api_key, prompt + f"\n\n【再指示】前回は長すぎたか、URLが正しく入っていませんでした。{url} をそのまま1回入れ、全体を240単位以内にしてください。", max_tokens=900)
    if url not in s.get("post", ""):
        raise ValueError("udemy post missing course URL")
    return s


def main():
    api_key = os.environ["ANTHROPIC_API_KEY"]
    today = datetime.datetime.now(JST).date()
    removed = purge_duplicates(today)
    if removed:
        print("Removed duplicate queued posts (will regenerate):\n" + "\n".join(removed))
    avoid = used_terms()
    made = []

    for i in range(7):
        d = today + datetime.timedelta(days=i)
        date = d.isoformat()
        wd = d.weekday()  # Mon=0 .. Sun=6

        # morning
        mtxt = os.path.join(ROOT, "queue", f"{date}-morning.txt")
        mposted = os.path.join(ROOT, "posted", f"{date}-morning.txt")
        if not os.path.exists(mtxt) and not os.path.exists(mposted):
            try:
                s = gen_morning(api_key, avoid)
                if _norm(s.get("term")) in {_norm(t) for t in avoid}:
                    raise ValueError(f"duplicate term returned: {s.get('term')}")
                open(mtxt, "w", encoding="utf-8").write(s["post"].strip())
                render("make_card.py", {k: s[k] for k in ("term", "sub", "desc", "diagram") if k in s}
                       | ({"term_size": s["term_size"]} if s.get("term_size") else {}),
                       os.path.join(ROOT, "queue", f"{date}-morning.png"))
                avoid.add(s.get("term", "").strip())
                made.append(f"{date} morning: {s.get('term')}")
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {date} morning failed: {e}", file=sys.stderr)

        # night
        ntxt = os.path.join(ROOT, "queue", f"{date}-night.txt")
        nposted = os.path.join(ROOT, "posted", f"{date}-night.txt")
        npng = os.path.join(ROOT, "queue", f"{date}-night.png")
        campaign = d <= CAMPAIGN_END

        # Night slot by weekday (outside the NESPE campaign window):
        #   Mon/Thu -> Udemy講座の紹介(5講座ローテーション, text only),
        #   Tue/Fri -> InfraGym, else -> career.
        # Campaign (if active) overrides all. Udemy days replace an existing
        # night that isn't that day's Udemy course (e.g. old Kindle posts);
        # other days only fill gaps.
        udemy = udemy_course_for(d) if wd in (0, 3) else None
        ntext = open(ntxt, encoding="utf-8").read() if os.path.exists(ntxt) else ""
        already_campaign = LP_URL[:22] in ntext
        already_udemy = udemy is not None and udemy[0]["url"] in ntext
        # Kindle(Amazon)の宣伝が残っていたら曜日に関係なく作り直す
        stale_kindle = "amazon.co.jp" in ntext
        do_night = (
            not os.path.exists(nposted)
            and (
                (campaign and not already_campaign)
                or (not campaign and udemy is not None and not already_udemy)
                or (not campaign and udemy is None and (not ntext or stale_kindle))
            )
        )
        if do_night:
            try:
                if campaign:
                    angle = CAMPAIGN_ANGLES[i % len(CAMPAIGN_ANGLES)]
                    s = gen_campaign(api_key, angle)
                    open(ntxt, "w", encoding="utf-8").write(s["post"].strip())
                    render("make_campaign_card.py",
                           {k: s[k] for k in ("badge", "last", "headline", "points", "cta_big") if k in s}
                           | ({"head_size": s["head_size"]} if s.get("head_size") else {}),
                           npng)
                    made.append(f"{date} night: campaign")
                elif udemy is not None:  # Mon/Thu -> Udemy course (text only, link card)
                    course, angle = udemy
                    s = gen_udemy(api_key, course, angle)
                    open(ntxt, "w", encoding="utf-8").write(s["post"].strip())
                    if os.path.exists(npng):  # ensure text-only (drop any stale card)
                        os.remove(npng)
                    made.append(f"{date} night: udemy({course['key']})")
                elif wd in (1, 4):  # Tue / Fri -> InfraGym promo + banner
                    pattern = "game" if wd == 1 else "pain"
                    s = gen_infragym(api_key, pattern)
                    open(ntxt, "w", encoding="utf-8").write(s["post"].strip())
                    subprocess.run(["cp", INFRAGYM_BANNER, npng], check=True)
                    made.append(f"{date} night: infragym({pattern})")
                else:
                    s = gen_career(api_key, CAREER_THEMES[d.toordinal() % len(CAREER_THEMES)], recent_texts("night"))
                    open(ntxt, "w", encoding="utf-8").write(s["post"].strip())
                    render("make_career_card.py",
                           {k: s[k] for k in ("badge", "headline", "body") if k in s}
                           | ({"head_size": s["head_size"]} if s.get("head_size") else {}),
                           npng)
                    made.append(f"{date} night: career")
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {date} night failed: {e}", file=sys.stderr)

        # afternoon (15:00) -> daily whoami 年収診断 promo (text only, OGP card)
        atxt = os.path.join(ROOT, "queue", f"{date}-afternoon.txt")
        aposted = os.path.join(ROOT, "posted", f"{date}-afternoon.txt")
        apng = os.path.join(ROOT, "queue", f"{date}-afternoon.png")
        already_whoami = os.path.exists(atxt) and "whoami-jobs.com/shindan" in open(atxt, encoding="utf-8").read()
        if not os.path.exists(aposted) and not already_whoami:
            try:
                angle = WHOAMI_ANGLES[d.toordinal() % len(WHOAMI_ANGLES)]
                s = gen_whoami(api_key, angle)
                open(atxt, "w", encoding="utf-8").write(s["post"].strip())
                if os.path.exists(apng):  # text-only (let X show the OGP link card)
                    os.remove(apng)
                made.append(f"{date} afternoon: whoami")
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {date} afternoon failed: {e}", file=sys.stderr)

        # evening (18:00) -> daily RackShare promo + card
        etxt = os.path.join(ROOT, "queue", f"{date}-evening.txt")
        eposted = os.path.join(ROOT, "posted", f"{date}-evening.txt")
        epng = os.path.join(ROOT, "queue", f"{date}-evening.png")
        if not os.path.exists(etxt) and not os.path.exists(eposted):
            try:
                angle = RACKSHARE_ANGLES[d.toordinal() % len(RACKSHARE_ANGLES)]
                s = gen_rackshare(api_key, angle)
                open(etxt, "w", encoding="utf-8").write(s["post"].strip())
                render("make_rackshare_card.py",
                       {k: s[k] for k in ("badge", "headline", "points", "cta_big") if k in s}
                       | ({"head_size": s["head_size"]} if s.get("head_size") else {}),
                       epng)
                made.append(f"{date} evening: rackshare")
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {date} evening failed: {e}", file=sys.stderr)

    print("Generated:\n" + ("\n".join(made) if made else "(nothing — all 7 days already filled)"))


if __name__ == "__main__":
    main()
