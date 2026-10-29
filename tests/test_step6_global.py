"""Step 6: a convention on the second board is found from outside it, and ACL limits are visible."""


def test_second_board_holds_three_invented_conventions(loadj):
    b = loadj("step6/board2.json")
    assert len(b["decision_nodes"]) == 3
    assert b["commit"]["data"]["status"] == "committed"


def test_global_query_finds_the_expected_convention_on_the_other_board(loadj):
    g = loadj("step6/global-discovery.json")
    assert len(g["queries"]) == 2
    for q in g["queries"]:
        assert q["top_board_is_second_board"] is True
        assert q["top_is_expected"] is True


def test_waiting_for_indexing_is_recorded(loadj):
    for q in loadj("step6/global-discovery.json")["queries"]:
        assert q["attempts"] >= 1 and q["seconds_until_result_or_timeout"] >= 0


def test_query_restricted_to_first_board_never_returns_second_board(loadj):
    g = loadj("step6/global-discovery.json")
    second = g["second_board_id"]
    for q in g["queries"]:
        assert all(r["board_id"] != second for r in q["result_restricted_to_first_board"]["data"]["results"])


def test_identity_with_first_board_access_only_cannot_see_second_board(loadj):
    g = loadj("step6/global-discovery.json")
    results = g["recaller_first_board_only_view"]["data"]["results"]
    assert all(r["board_id"] != g["second_board_id"] for r in results)


def test_discovery_is_healthy_with_no_dead_letters(loadj):
    g = loadj("step6/global-discovery.json")
    assert g["first_board_health_discovery_state"] == "healthy"
    assert g["first_board_global_outbox"] == 0
