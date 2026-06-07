INSTRUCTION_PARSED_PATH = "me_instruction_parsed_path"
INSTRUCTION_MD_PATH = "me_instruction_md_path"
INSTRUCTION_NAME = "me_instruction_name"
MODEL_REPORT = "me_model_report"
DETAIL_DIALOGUES = "detail_dialogues"


def clear_report_state(st):
    for key in [MODEL_REPORT, DETAIL_DIALOGUES]:
        if key in st.session_state:
            del st.session_state[key]


def set_instruction_state(st, parsed_path: str, md_path: str, name: str):
    prev = st.session_state.get(INSTRUCTION_NAME)
    if prev and prev != name:
        clear_report_state(st)
    st.session_state[INSTRUCTION_PARSED_PATH] = parsed_path
    st.session_state[INSTRUCTION_MD_PATH] = md_path
    st.session_state[INSTRUCTION_NAME] = name

