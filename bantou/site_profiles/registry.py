# -*- coding: utf-8 -*-
import re

URL_RE = re.compile(r"https?://\S+", re.I)
SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*([\"']?)([^\"'\s>]+)\1", re.I)
IFRAME_SRC_RE = re.compile(r"<iframe\b[^>]*\bsrc\s*=\s*([\"']?)([^\"'\s>]+)\1", re.I)
HALF_HEAD_LINK_RE = re.compile(
    r"<a\b[^>]*\bhref\s*=\s*([\"']?)([^\"'\s>]+)\1[^>]*>(?:(?!</a>).)*半\s*头(?:(?!</a>).)*</a>",
    re.I | re.S,
)
STRDECODE_RE = re.compile(r"strdecode\s*\(\s*([\"'])([^\"']+)\1\s*\)", re.I)
HALF_HEAD_KEYWORD_RE = re.compile(r"(?:秒杀|必杀|绝杀|稳杀|杀).{0,8}?半头", re.I | re.S)
NON_HALF_HEAD_COLUMN_RE = re.compile(
    r"(?:杀半波|半波|杀尾|尾尾|复试尾|拖尾|杀肖|六肖|三肖|九肖|七肖|八码|六肖中|"
    r"三头中特|四尾三头|头中特|平特一肖|平特|特码|肖中特|中特|绝密\d*肖|亡肖|肉菜草肖)",
    re.I,
)
OPEN_INFO_RE = re.compile(r"开\s*[:：?？]?\s*([鼠牛虎兔龙蛇马羊猴鸡狗猪]?\s*\d{2,4})")
STRICT_HALF_HEAD_RE = re.compile(
    r"(?:秒杀|必杀|绝杀|稳杀|杀)[\s\S]{0,12}?半头[\s\S]{0,50}?([0-4])\s*头\s*(单|双)",
    re.I,
)
DEFAULT_KEYWORDS = ("杀半头", "秒杀半头", "必杀半头", "绝杀半头", "稳杀半头")

SITE_RENDERED_PAGE_AUTHORITY_URLS = {
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/116162",
    "https://hbwtl.7xzry-2gul3-olawdt.xyz/topic/227014.html",
    "https://rh2fgz.w043g-ql5mr-lfxblm.work/topic/499784.html",
    "https://sfch0f.2c6xk-l5fko-klefxa.work/topic/453945.html",
    "https://54matx.ulky8-iau8d-tzdsok.xyz/topic/225400.html",
    "https://ryfbdty.p4a53-f1hew-diwcrg.xyz:16677/topic/453368.html",
    "https://jogavu.6bl6s-ilo1w-yfnvvl.work:16677/topic/678626.html",
    "https://tulprhfc.wghcb-bnmgm-hyymaz.work:16655/topic/324701.html",
    "https://kqfmnjht.ip6et-0zvu7-gpqkrf.work:16677/topic/253144.html",
    "https://4m6dz.r1wvw-qncts-admwen.xyz/topic/222781.html",
    "https://vhgswwe.7rdnv-4uc7h-yshpkm.xyz:16677/topic/447905.html",
    "https://kulipur.l5paz-a0o8v-uozmmd.xyz:16677/topic/435504.html",
    "https://fptnapl.o7l2d-gr6ew-tvgvep.xyz:16677/topic/349647.html",
    "https://kjkkzzg.eiu7u-3edk2-gjzmrl.xyz:16677/topic/446873.html",
    "https://dhqjbz.uxec9-jxs3h-fomubo.work:16677/topic/250855.html",
    "https://whsbrmz.qclrc-4mk42-vnxbyg.work:16677/topic/248024.html",
    "https://fhrtnoy.10cus-ki4mn-mlcyap.xyz:16677/topic/447346.html",
    "https://knhlnvo.zvdsi-8qf2t-wchuxk.xyz:16677/topic/437752.html",
    "https://bdxufda.po4ai-dqhr0-mljzdr.work:16655/topic/225370.html",
    "https://ripzotqz.prm9k-tor19-vowopt.xyz:16677/topic/210745.html",
    "https://e7rzi6.ic890-g0deq-lbrbfs.work/topic/226265.html",
    "https://vbxl5.wp5pl-3ztz5-cwgbti.xyz/topic/216096.html",
    "https://myvvqq.g25n3-cpae1-psslpy.work/topic/206462.html",
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/206464.html",
    "https://pyjgoe.burj6-ovh80-gurlas.xyz:16677/topic/697235.html",
    "https://xxn08n.w2jqr-rbl71-ngvkmq.work/topic/453964.html",
    "https://pvxiftuf.yumkw-u4s81-hpytyz.work:16677/",
    "https://e7rzi6.vkzoy-tj5wf-umxqmx.work/topic/453616.html",
    "https://qzpwvvvb.a3qgk-l2h5k-opahdg.xyz:16677/topic/254838.html",
    "https://qzpwvvvb.a3qgk-l2h5k-opahdg.xyz:16677/topic/254821.html",
    "https://cthvktrb.am9a6-vk0h6-lwbxab.xyz:16677/",
    "https://ebhxngwb.2ljj5-vdh8s-gbvkgl.xyz:16677/topic/255949.html",
    "https://stkfbbns.yrfhc-z5x6i-ykoqqu.xyz:16677/topic/251258.html",
    "https://bnvzafsk.nnmu7-qytv7-qjorxd.xyz:16677/topic/450973.html",
    "https://43666.886677a.app:2563/htm/bbs/top080.html",
    "https://pkrcani.cm4li-554vw-zuncoa.xyz:16677/topic/469066.html",
    "https://wojedcr.ltslh-5g80v-eeujep.xyz:16677/topic/805239.html",
    "https://mkhomxq.gqmpb-vuxji-pfnheu.work:16677/topic/510826.html",
    "https://bzdolgna.0115r-u1nk5-zioots.xyz:16677/topic/250880.html",
    "https://xoxtpupt.bvptr-i3mv8-pbjxin.work:17455/topic/257049.html",
    "https://xoxtpupt.bvptr-i3mv8-pbjxin.work:17455/topic/393298.html",
    "https://huqtzej.vvlq2-j4i8n-lisghq.xyz:16677/topic/281481.html",
    "https://xmdrbud.eqpr2-6tpvi-pjqztv.xyz:16677/topic/320718.html",
    "https://xmdrbud.eqpr2-6tpvi-pjqztv.xyz:16677/",
    "https://cdsgyr.6xzb4-onz45-zlnoys.xyz:16677/topic/282008.html",
    "https://ocnrhq.du156-vb27w-tmhsed.xyz:16677/",
    "https://rqvvaxwq.w30m7-xd23l-ebrbbj.xyz/topic/768624.html",
    "https://opfeal.zbwno-faau4-zilwkd.xyz:16677/topic/930772.html",
    "https://kxglojup.fao5v-9u0oz-okhubb.work:16677/topic/782068.html",
    "https://xuknerw.fu5qv-a7f7o-nxmebt.work:16633/topic/272856.html",
}

CAIYUNTONG_URL = "https://fnulucd.s2569-p869e-eekdks.xyz:16677/"
GUANGDONG_BAER_URL = "https://besjbec.6328v-8pwlk-jzhgyz.work:16677/#am"
SEWAI_TAOYUAN_URL = "https://667755.xn--q9ja6j.xn--q9jyb4c/gsb/030.html"
MENGXIAOMENG_URL = "https://xmdrbud.eqpr2-6tpvi-pjqztv.xyz:16677/"
SITE_BROWSER_HTML_URLS = {CAIYUNTONG_URL, GUANGDONG_BAER_URL, MENGXIAOMENG_URL}
SITE_BROWSER_HTML_WAIT_UNTIL = {
    CAIYUNTONG_URL: "domcontentloaded",
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/116162": "networkidle",
    GUANGDONG_BAER_URL: "load",
    MENGXIAOMENG_URL: "domcontentloaded",
    "https://opfeal.zbwno-faau4-zilwkd.xyz:16677/topic/930772.html": "domcontentloaded",
    "https://sadoleu.rznla-fgwyr-nzqalp.xyz:16677/topic/287642.html": "domcontentloaded",
    "https://vqyjnlug.qt1u6-vqjjl-vkdnzw.work:16655/topic/650194.html": "domcontentloaded",
    "https://sqddimfu.evs71-kia2b-gshsdc.xyz:16677/topic/205530.html": "domcontentloaded",
    "https://kfsujebc.djiz8-4tqt6-hubani.xyz:16677/topic/280922.html": "domcontentloaded",
    "https://xuknerw.fu5qv-a7f7o-nxmebt.work:16633/topic/291093.html": "domcontentloaded",
    "https://vmfvzmh.7jh1y-qgjk8-lavfxb.work:16677/topic/782033.html": "domcontentloaded",
    "https://oigqsvqs.2n3pw-mjk5d-wndmjh.xyz:16677/topic/287383.html": "domcontentloaded",
    "https://tlwggkde.dp86b-grpqw-uiiazp.work:17466/topic/247714.html": "domcontentloaded",
}
DEDICATED_RENDERED_SITE_RULES = {
    "https://s4wqb.p2b6h-0xj4v-suxrzo.xyz/topic/206519.html": "topic-content",
    "https://zwhzkjo.fc4fh-otded-nvhceu.xyz:16677/topic/472642.html": "content",
    "https://cpvqejp.avdja-la48l-xnsdva.xyz:16677/topic/336839.html": "topic-content",
    "https://sadoleu.rznla-fgwyr-nzqalp.xyz:16677/topic/287642.html": "detail_info_forum2_item",
    "https://vqyjnlug.qt1u6-vqjjl-vkdnzw.work:16655/topic/650194.html": "content",
    "https://xxn08n.w2jqr-rbl71-ngvkmq.work/": "swiper-slide",
    "https://kfsujebc.djiz8-4tqt6-hubani.xyz:16677/topic/280922.html": "content",
    "https://xuknerw.fu5qv-a7f7o-nxmebt.work:16633/topic/291093.html": "topic-content",
    "https://vmfvzmh.7jh1y-qgjk8-lavfxb.work:16677/topic/782033.html": "topic-content",
    "https://peubwtt.t3vdj-h3294-qpbmtj.work:16677/#am": "dz_content08",
    "https://alvjak.uh1h2-ru1qt-cyscbt.xyz:16677/topic/328416.html": "detail_info_forum2_item",
    "https://xuknerw.fu5qv-a7f7o-nxmebt.work:16633/topic/272899.html": "topic-content",
    "https://sqddimfu.evs71-kia2b-gshsdc.xyz:16677/topic/205530.html": "topic-content",
    "https://oigqsvqs.2n3pw-mjk5d-wndmjh.xyz:16677/topic/287383.html": "content",
    "https://fflkqo.fvi38-kyblx-znvboh.work:17466/topic/1008749.html": "topic-content",
    "https://269x6s.k4x2w-1o62c-peefnm.work/topic/206456.html": "topic-content",
    "https://uwkzbx.2pgdu-vva8o-nkhrzz.xyz:16677/topic/308018.html": "detail_info_forum2_item",
    "https://epsyvycz.ff10o-370zd-qssnum.xyz:16677/topic/328057.html": "detail_info_forum2_item",
    "https://cdsgyr.6xzb4-onz45-zlnoys.xyz:16677/topic/328425.html": "detail_info_forum2_item",
    "https://njkzdcwj.nql6i-8t6su-hytife.xyz:16677/topic/324619.html": "detail_info_forum2_item",
    "https://eudkyp.luqv0-yf46s-xrnpkz.xyz:16677/topic/324148.html": "detail_info_forum2_item",
    "https://sadoleu.rznla-fgwyr-nzqalp.xyz:16677/topic/656863.html": "detail_info_forum2_item",
    "https://ntvjzt.gau41-qu6jy-sotyug.work:16677/topic/309356.html": "detail_info_forum2_item",
    "https://gt6.59197c.com:8443/tie1/t30.html": "page",
    "https://667755.xn--q9ja6j.xn--q9jyb4c/gsb/030.html": "content",
    "https://62cc.xn--cckc4dwc5inab2m.xn--q9jyb4c/6dgsb/0002.html": "topic-content",
    "https://fbgbfg.www27521c.com:8443/gsb/am05.html": "page",
    "https://2.www39169b.com:888/gsbl/s23.html": "page",
    "https://tlwggkde.dp86b-grpqw-uiiazp.work:17466/topic/247714.html": "page",
}
DEDICATED_RENDERED_AUTHOR_CONTEXT_URLS = {
    "https://s4wqb.p2b6h-0xj4v-suxrzo.xyz/topic/206519.html",
    "https://zwhzkjo.fc4fh-otded-nvhceu.xyz:16677/topic/472642.html",
    "https://cpvqejp.avdja-la48l-xnsdva.xyz:16677/topic/336839.html",
    "https://vqyjnlug.qt1u6-vqjjl-vkdnzw.work:16655/topic/650194.html",
    "https://kfsujebc.djiz8-4tqt6-hubani.xyz:16677/topic/280922.html",
    "https://xuknerw.fu5qv-a7f7o-nxmebt.work:16633/topic/291093.html",
    "https://vmfvzmh.7jh1y-qgjk8-lavfxb.work:16677/topic/782033.html",
    "https://xuknerw.fu5qv-a7f7o-nxmebt.work:16633/topic/272899.html",
    "https://sqddimfu.evs71-kia2b-gshsdc.xyz:16677/topic/205530.html",
    "https://oigqsvqs.2n3pw-mjk5d-wndmjh.xyz:16677/topic/287383.html",
    "https://269x6s.k4x2w-1o62c-peefnm.work/topic/206456.html",
    "https://62cc.xn--cckc4dwc5inab2m.xn--q9jyb4c/6dgsb/0002.html",
}
DEDICATED_RENDERED_PAGE_IDENTITIES = {
    "https://xxn08n.w2jqr-rbl71-ngvkmq.work/": "澳门周公神算",
    "https://peubwtt.t3vdj-h3294-qpbmtj.work:16677/#am": "澳门跑狗",
    "https://fflkqo.fvi38-kyblx-znvboh.work:17466/topic/1008749.html": "诸葛亮",
    "https://eudkyp.luqv0-yf46s-xrnpkz.xyz:16677/topic/324148.html": "内幕资料[半波半头]免费公开",
    "https://gt6.59197c.com:8443/tie1/t30.html": "缘起缘灭",
    "https://fbgbfg.www27521c.com:8443/gsb/am05.html": "山野独行",
    "https://2.www39169b.com:888/gsbl/s23.html": "虚情假意",
    "https://tlwggkde.dp86b-grpqw-uiiazp.work:17466/topic/247714.html": "澳门聚宝盆",
}
DEDICATED_RENDERED_ALTERNATE_DATA_ANCHORS = {
    "https://269x6s.k4x2w-1o62c-peefnm.work/topic/206456.html": ("秒杀",),
}
DEDICATED_RENDERED_CURRENT_SERIES_URLS = {
    "https://cpvqejp.avdja-la48l-xnsdva.xyz:16677/topic/336839.html",
    "https://zwhzkjo.fc4fh-otded-nvhceu.xyz:16677/topic/472642.html",
    "https://vqyjnlug.qt1u6-vqjjl-vkdnzw.work:16655/topic/650194.html",
    "https://kfsujebc.djiz8-4tqt6-hubani.xyz:16677/topic/280922.html",
    "https://vmfvzmh.7jh1y-qgjk8-lavfxb.work:16677/topic/782033.html",
    "https://oigqsvqs.2n3pw-mjk5d-wndmjh.xyz:16677/topic/287383.html",
}
SITE_CURRENT_SERIES_PLACEHOLDER_URLS = {
    "https://kjkkzzg.eiu7u-3edk2-gjzmrl.xyz:16677/topic/446873.html",
}

DYNAMIC_RECORD_AUTHOR_ALIASES = {
    "https://qvuuqqs.8imf7-hteuh-ylwuqv.xyz/#/users/11993/references/15358093": (
        "财富榜资料员",
    ),
}
DYNAMIC_RECORD_TOPIC_ALIASES = {
    "https://qvuuqqs.8imf7-hteuh-ylwuqv.xyz/#/users/11993/references/15358093": (
        "财富榜",
    ),
}
DYNAMIC_RECORD_SUBTOPIC_ALIASES = {
    "https://qvuuqqs.8imf7-hteuh-ylwuqv.xyz/#/users/11993/references/15358093": (
        "必杀半头",
    ),
}
WUZHUANXINGYI_URL = "https://ocnrhq.du156-vb27w-tmhsed.xyz:16677/"
WUZHUANXINGYI_CARD_LABELS = ("星移物换", "物转星移")
BABA_FORUM_URL = "https://43666.886677a.app:2563/htm/bbs/top080.html"
BABA_FORUM_DATA_URL = "https://43666.886677a.app:2563/main/bbs/080.html"
SHENZHEN_FUTAN_URL = "https://128.241.252.220:9201/tz/bbsjs/080.html"
SITE_IFRAME_PAGE_AUTHORITY_URLS = {BABA_FORUM_URL}

# A site may share the strict parsing engine, but it must still declare its own
# configuration identity and anchors in sites.json.
SUPPORTED_PARSER_IDS = {
    "strict_half_head",
    "caiyuntong_macau",
    "guangdong_baer_left_half_head",
    "sewai_taoyuan",
    "shenzhen_futan_half_head",
    "wuzhuanxingyi_embedded",
}


def _special_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I)


SITE_SPECIAL_VALUE_PATTERNS = {
    "https://hbwtl.7xzry-2gul3-olawdt.xyz/topic/227014.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]\s*必杀半头\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*开(?:(?!(?<!\d)\d{1,4}期)[^\n]){0,12}"),
    ),
    "https://kulipur.l5paz-a0o8v-uozmmd.xyz:16677/topic/435504.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[\s\S]{0,20}?必杀半头[\s\S]{0,30}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[\s\S]{0,20}?开[^\n]{0,12}"),
    ),
    "https://kjkkzzg.eiu7u-3edk2-gjzmrl.xyz:16677/topic/446873.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*必杀半头\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*(?:[鼠牛虎兔龙蛇马羊猴鸡狗猪]\s*)?[?？]?\s*\d{2,4}(?:\s*[对准中√错×xX])?"),
    ),
    "https://dhqjbz.uxec9-jxs3h-fomubo.work:16677/topic/250855.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,20}?绝杀半头[^\n]{0,30}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://myvvqq.g25n3-cpae1-psslpy.work/topic/206462.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,20}?绝杀半头[^\n]{0,30}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://sqddimfu.evs71-kia2b-gshsdc.xyz:16677/topic/205530.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,30}?必杀半头[^\n]{0,30}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://qzpwvvvb.a3qgk-l2h5k-opahdg.xyz:16677/topic/254838.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,40}?绝杀半头[^\n]{0,30}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://bb5.www87127b.com:8443/bbs/31.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,30}?必杀半头[^\n]{0,30}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://knhlnvo.zvdsi-8qf2t-wchuxk.xyz:16677/topic/437752.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,30}?绝杀半头[^\n]{0,30}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://uwkzbx.2pgdu-vva8o-nkhrzz.xyz:16677/topic/308018.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,20}?(?:㊣|正)\s*秒杀[^\n]{0,20}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://tulprhfc.wghcb-bnmgm-hyymaz.work:16655/topic/324701.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,12}?ღ\s*秒杀\s*ღ[^\n]{0,12}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://269x6s.k4x2w-1o62c-peefnm.work/topic/206456.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,12}?ღ\s*秒杀\s*ღ[^\n]{0,12}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://bnvzafsk.nnmu7-qytv7-qjorxd.xyz:16677/topic/450973.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,30}?绝杀(?:㊣|正)?半头[^\n]{0,20}?([0-4])\s*头\s*(单|双)[^\n]{0,20}?开\s*[:：]?[^\n]{0,12}"),
    ),
    "https://pkrcani.cm4li-554vw-zuncoa.xyz:16677/topic/469066.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,30}?稳杀半头[^\n]{0,30}?(?:【|\[|〖)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\]|〗)[^\n]{0,20}?开\s*[:：]?[^\n]{0,12}"),
    ),
    "https://kfsujebc.djiz8-4tqt6-hubani.xyz:16677/topic/280922.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,30}?稳杀半头[^\n]{0,30}?(?:【|\[)?\s*([0-4])\s*头\s*(单|双)\s*数?\s*(?:】|\])?[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://ebhxngwb.2ljj5-vdh8s-gbvkgl.xyz:16677/topic/255949.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,20}?必杀半头[^\n]{0,20}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://2.www39169b.com:888/gsbl/s23.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]\s*必杀半头\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*开[^\n]{0,12}"),
    ),
    "https://a.995546.com/gsb.aspx?id=amjyb089": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,20}?(?:稳杀半头|绝杀半头)[^\n]{0,30}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://a.909922.com/bbs.aspx?id=amsmh058": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[^\n]{0,20}?(?:稳杀半头|绝杀半头)[^\n]{0,30}?(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://ocnrhq.du156-vb27w-tmhsed.xyz:16677/": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*(?:【|\[)\s*绝杀半头\s*(?:】|\])\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://43666.886677a.app:2563/htm/bbs/top080.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]\s*🍀?\s*瞬杀半头\s*🍀?\s*开\s*[:：?？]?\s*(?:[鼠牛虎兔龙蛇马羊猴鸡狗猪]\s*)?[?？]?\s*\d{2,4}\s*[对准中√错×xX]\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])"),
    ),
    "https://cthvktrb.am9a6-vk0h6-lwbxab.xyz:16677/": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]\s*绝杀半头\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*开\s*[:：?？]?\s*(?:[鼠牛虎兔龙蛇马羊猴鸡狗猪]\s*)?[?？]?\s*\d{2,4}\s*[对准中赢√错×xX]"),
    ),
    "https://epsyvycz.ff10o-370zd-qssnum.xyz:16677/topic/328057.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*杀\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://cdsgyr.6xzb4-onz45-zlnoys.xyz:16677/topic/328425.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期[:：]?\s*杀\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])(?:【|\[)[^\]\n]{1,8}(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://njkzdcwj.nql6i-8t6su-hytife.xyz:16677/topic/324619.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*杀\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://eudkyp.luqv0-yf46s-xrnpkz.xyz:16677/topic/324148.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*杀\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])(?:【|\[)[^\]\n]{1,8}(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://alvjak.uh1h2-ru1qt-cyscbt.xyz:16677/topic/328416.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*杀\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://sadoleu.rznla-fgwyr-nzqalp.xyz:16677/topic/656863.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*杀\s*(?:【|\[)?\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])?\s*\+{3}\s*杀[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://mflmcobome.26222hi.app:2569/htm/bbs/top080.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]\s*(?:⚡️?\s*秒杀半头\s*⚡️?|❄️?\s*绝杀半头\s*❄️?)\s*开\s*[:：?？]?\s*(?:[鼠牛虎兔龙蛇马羊猴鸡狗猪]\s*)?[?？]?\s*\d{2,4}\s*[对准中√错×xX]\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])"),
    ),
    "https://peubwtt.t3vdj-h3294-qpbmtj.work:16677/#am": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*(?:绝杀半头|必杀半头)\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://993345.com/gsb.aspx?id=024": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*✿\s*稳杀半头\s*✿\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://rqvvaxwq.w30m7-xd23l-ebrbbj.xyz/topic/768624.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*(?:【|\[)\s*绝杀半头\s*(?:】|\])\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://opfeal.zbwno-faau4-zilwkd.xyz:16677/topic/930772.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*～～绝杀半头～～\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://fflkqo.fvi38-kyblx-znvboh.work:17466/topic/1008749.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*(?:【|\[)\s*绝杀半头\s*(?:】|\])\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://kxglojup.fao5v-9u0oz-okhubb.work:16677/topic/782068.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*必杀半头\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://xuknerw.fu5qv-a7f7o-nxmebt.work:16633/topic/272899.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*★必杀半头★\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://xuknerw.fu5qv-a7f7o-nxmebt.work:16633/topic/272856.html": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*[:：]?\s*必杀半头\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])[^\n]{0,20}?开[^\n]{0,12}"),
    ),
    "https://a.ttss.vip/list.aspx?id=33": (
        _special_pattern(r"(?<!\d)(\d{1,4})期\s*◆\s*满脸春色\s*㊣\s*精杀\s*[:：]\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*开[^\n]{0,12}"),
    ),
    "https://4.48kk49.com:1888/Article/ar_content/id/209/tid/3.html": (
        _special_pattern(
            r"(?<!\d)(\d{1,4})期\s*白姐杀半头\s*[:：]?\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*开\s*(?:[鼠牛虎兔龙蛇马羊猴鸡狗猪]\s*)?(?:\d{2,4}|[?？]{2,})(?:\s*[对准中√错×xX])?"
        ),
    ),
    "https://4.48kk49.com:1888/Article/ar_content/id/198/tid/4.html": (
        _special_pattern(
            r"(?<!\d)(\d{1,4})期\s*杀\s*[:：]?\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*开\s*(?:[鼠牛虎兔龙蛇马羊猴鸡狗猪]\s*)?(?:\d{2,4}|[?？]{2,})(?:\s*[对准中√错×xX])?"
        ),
    ),
    "https://4.48kk49.com:1888/Article/ar_content/id/145/tid/8.html": (
        _special_pattern(
            r"(?<!\d)(\d{1,4})期\s*杀\s*[:：]?\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*开\s*(?:[鼠牛虎兔龙蛇马羊猴鸡狗猪]\s*)?(?:\d{2,4}|[?？]{2,})(?:\s*[对准中√错×xX])?"
        ),
    ),
    "https://4.48kk49.com:1888/Article/ar_content/id/134/tid/9.html": (
        _special_pattern(
            r"(?<!\d)(\d{1,4})期\s*杀半头[\s★☆*]*[:：]?\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*开\s*(?:[鼠牛虎兔龙蛇马羊猴鸡狗猪]\s*)?(?:\d{2,4}|[?？]{2,})(?:\s*[对准中√错×xX])?"
        ),
    ),
    "https://4.48kk49.com:1888/Article/ar_content/id/545/tid/35.html": (
        _special_pattern(
            r"(?<!\d)(\d{1,4})期\s*财神爷㊣秒杀\s*[:：]?\s*(?:【|\[)\s*([0-4])\s*头\s*(单|双)\s*(?:】|\])\s*开\s*(?:[鼠牛虎兔龙蛇马羊猴鸡狗猪]\s*)?(?:\d{2,4}|[?？]{2,})(?:\s*[对准中√错×xX])?"
        ),
    ),
}

SITE_TARGET_PLACEHOLDER_URLS = {
    "https://a.ttss.vip/list.aspx?id=33",
    "https://4.48kk49.com:1888/Article/ar_content/id/209/tid/3.html",
    "https://4.48kk49.com:1888/Article/ar_content/id/198/tid/4.html",
    "https://4.48kk49.com:1888/Article/ar_content/id/145/tid/8.html",
    "https://4.48kk49.com:1888/Article/ar_content/id/134/tid/9.html",
    "https://4.48kk49.com:1888/Article/ar_content/id/545/tid/35.html",
}
