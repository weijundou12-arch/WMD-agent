from app.agents.context import contextualize_question
from app.schemas.chat import ConversationTurn


def test_resolves_chinese_place_travel_follow_up():
    question, used_context, _ = contextualize_question(
        "那么我想去这个地方旅游，有什么推荐",
        [
            ConversationTurn(
                question="介绍一下中国山东博兴",
                answer="博兴县是山东省滨州市下辖的县级行政区。",
                evidence_titles=["山东省人民政府 博兴县", "博兴县 - 维基百科"],
            )
        ],
    )

    assert used_context is True
    assert "博兴县" in question
    assert "旅游" in question
    assert "推荐" in question


def test_resolves_place_topic_before_failed_follow_up():
    question, used_context, _ = contextualize_question(
        "再给我推荐一条路线",
        [
            ConversationTurn(
                question="介绍一下中国山东博兴",
                answer="博兴县是山东省滨州市下辖的县级行政区。",
                evidence_titles=["山东省人民政府 博兴县"],
            ),
            ConversationTurn(
                question="那么我想去这个地方旅游，有什么推荐",
                answer="本次没有拿到可核验的在线网页结果。",
                evidence_titles=["Live web search unavailable"],
            ),
        ],
    )

    assert used_context is True
    assert "博兴县" in question
    assert "旅游" in question
    assert "推荐" in question


def test_keeps_latest_heze_topic_for_restaurant_follow_up():
    question, used_context, _ = contextualize_question(
        "推荐具体的景点和饭店",
        [
            ConversationTurn(
                question="介绍一下中国山东博兴",
                answer="博兴县是山东省滨州市下辖的县级行政区。",
                evidence_titles=["山东省人民政府 博兴县"],
            ),
            ConversationTurn(
                question="介绍一下中国山东菏泽市",
                answer="菏泽市，简称菏，古称曹州，是山东省下辖的地级市。",
                evidence_titles=["中文维基百科：菏泽市", "菏泽市人民政府门户网站"],
            ),
            ConversationTurn(
                question="如果我要去这玩三天，怎么推荐",
                answer="菏泽市更适合牡丹文化、鲁西南历史文化和周边短途游。",
                evidence_titles=["中文维基百科：菏泽市旅游", "菏泽市博物馆"],
            ),
        ],
    )

    assert used_context is True
    assert "菏泽市" in question
    assert "博兴县" not in question
    assert "饭店" in question


def test_skips_bad_place_context_and_recovers_heze():
    question, used_context, _ = contextualize_question(
        "再推荐几个饭店",
        [
            ConversationTurn(
                question="介绍一下中国山东菏泽市",
                answer="菏泽市，简称菏，古称曹州，是山东省下辖的地级市。",
                confidence="strong",
                evidence_titles=["中文维基百科：菏泽市", "菏泽市人民政府门户网站"],
            ),
            ConversationTurn(
                question="推荐具体的景点和饭店",
                answer="更成為台北市更适合做滨州/淄博周边短途游，优先推荐麻大湖。",
                confidence="moderate",
                evidence_titles=["台北市", "博兴县 - 维基百科：旅游"],
            ),
        ],
    )

    assert used_context is True
    assert "菏泽市" in question
    assert "博兴县" not in question
    assert "饭店" in question
