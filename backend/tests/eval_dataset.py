from pydantic_evals import Case

cases = [
    Case(
        name="nd135_scope",
        inputs="Nghị định 135/2026/NĐ-CP quy định về vấn đề gì?",
        expected_output="cơ chế chính sách tiền cho đơn vị điều độ hệ thống điện quốc gia",
    ),
    Case(
        name="nd135_legal_basis",
        inputs="Căn cứ pháp lý nào để ban hành Nghị định 135/2026/NĐ-CP?",
        expected_output="Luật Điện lực số 61/2024/QH15",
    ),
    Case(
        name="nd135_submitting_body",
        inputs="Nghị định 135/2026/NĐ-CP do Bộ nào trình?",
        expected_output="Bộ Công Thương",
    ),
    Case(
        name="nd135_effective_date",
        inputs="Nghị định 135/2026/NĐ-CP được ban hành ngày nào?",
        expected_output="07 tháng 4 năm 2026",
    ),
    Case(
        name="nd135_article1",
        inputs="Điều 1 của Nghị định 135/2026/NĐ-CP quy định về phạm vi điều chỉnh như thế nào?",
        expected_output="phạm vi điều chỉnh các cơ chế chính sách theo Luật Điện lực",
    ),
    Case(
        name="nd298_scope",
        inputs="Nghị định 298/2026/NĐ-CP quy định về vấn đề gì?",
        expected_output="chức năng nhiệm vụ quyền hạn cơ cấu tổ chức của Bộ Văn hóa Thể thao và Du lịch",
    ),
    Case(
        name="nd298_functions",
        inputs="Bộ Văn hóa, Thể thao và Du lịch có chức năng gì theo Nghị định 298?",
        expected_output="quản lý nhà nước về văn hóa gia đình thể dục thể thao du lịch báo chí",
    ),
    Case(
        name="nd298_submitting_body",
        inputs="Nghị định 298/2026/NĐ-CP do cơ quan nào trình?",
        expected_output="Bộ Văn hóa Thể thao và Du lịch",
    ),
    Case(
        name="nd298_effective_date",
        inputs="Nghị định 298/2026/NĐ-CP được ban hành ngày nào?",
        expected_output="27 tháng 7 năm 2026",
    ),
    Case(
        name="unrelated",
        inputs="Trái đất hình gì?",
        expected_output="I don't have enough information",
    ),
]
