from doc_parser.output.logger import Logger, build_log_txt


def test_logger_collects_lines_with_level_and_timestamp() -> None:
    logger = Logger()
    logger.log("INFO", "avviato")
    logger.log("ERROR", "fallito")
    assert len(logger.lines) == 2
    assert "[INFO] avviato" in logger.lines[0]
    assert "[ERROR] fallito" in logger.lines[1]


def test_logger_lines_is_a_copy() -> None:
    logger = Logger()
    logger.log("INFO", "x")
    lines = logger.lines
    lines.append("iniettata")
    assert "iniettata" not in logger.lines


def test_build_log_txt_italian_header() -> None:
    txt = build_log_txt(["[INFO] riga"], "it")
    assert "LOG DI GENERAZIONE" in txt
    assert "[INFO] riga" in txt


def test_build_log_txt_english_header() -> None:
    txt = build_log_txt(["[INFO] line"], "en")
    assert "GENERATION LOG" in txt
