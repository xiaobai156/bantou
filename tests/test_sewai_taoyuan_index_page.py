"""世外桃源每期换 /gsb/NNN.html：必须按当期从站内榜单现查页号。"""
from bantou.documents.collection import sewai_taoyuan_page_from_index

INDEX = """
document.writeln(" <li><a target=\\'_blank\\' class=\\'suffix\\' href=\\'/gsb/060.html\\'>");
document.writeln("269期:世外桃源<font color=\\'#0000FF\\'><span class=\\'zg\\'>【绝杀半头】</span></font>99中98</a></li>");
document.writeln(" <li><a target=\\'_blank\\' class=\\'suffix\\' href=\\'/gsb/085.html\\'>");
document.writeln("270期:世外桃源<font color=\\'#0000FF\\'><span class=\\'zg\\'>【绝杀半头】</span></font>99中98</a></li>");
document.writeln(" <li><a target=\\'_blank\\' class=\\'suffix\\' href=\\'/gsb/090.html\\'>");
document.writeln("271期:世外桃源<font color=\\'#0000FF\\'><span class=\\'zg\\'>【金牌七肖】</span></font>99中98</a></li>");
"""


def test_picks_page_listed_for_requested_issue():
    assert sewai_taoyuan_page_from_index(INDEX, 270) == "/gsb/085.html"
    assert sewai_taoyuan_page_from_index(INDEX, 269) == "/gsb/060.html"


def test_returns_none_when_issue_or_column_missing():
    assert sewai_taoyuan_page_from_index(INDEX, 268) is None
    assert sewai_taoyuan_page_from_index(INDEX, 271) is None
