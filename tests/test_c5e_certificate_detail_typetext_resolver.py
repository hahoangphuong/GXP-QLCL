from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.document.c5e_certificate_detail_typetext_resolver import (
    CRLF,
    TAB,
    CertificateDetailTranslationDictionary,
    CertificateDetailTypeTextError,
    del_last_if,
    del_last_if_ins,
    khong_dau,
    merge_text,
    resolve_certificate_detail_typetext,
    split_lines,
    translate_ve_daychuyen,
    translate_ve_diachi,
)


def _dictionary():
    return CertificateDetailTranslationDictionary(
        acchs="ĐđáÁ",
        rgchs="DdaA",
        matrices={
            "TV_Words": (
                ("Thuốc vô trùng|thuốc vô trùng",),
                ("Đóng gói",),
            ),
            "TA_Words": (
                ("Sterile Products",),
                ("Packaging",),
            ),
            "TV_Words2": (
                ("Đường",),
                ("Phường",),
            ),
            "TA_Words2": (
                ("Street",),
                ("Ward",),
            ),
            "TA_Words2_Loc": (
                ("T", "T"),
                ("", ""),
            ),
            "TV_Words4": (
                ("Bảo quản",),
            ),
            "TA_Words4": (
                ("Storage",),
            ),
            "TV_Words6": (
                ("GDP only",),
            ),
            "TA_Words6": (
                ("GDP",),
            ),
        },
    )


def _op(
    sequence,
    kind,
    raw_text="",
    branch=None,
):
    return SimpleNamespace(
        sequence=sequence,
        kind=kind,
        raw_text=raw_text,
        branch=branch,
    )


def _projection(
    operations,
    *,
    gxp_type="GMP",
):
    return SimpleNamespace(
        gxp_type=gxp_type,
        source_variant="certificate_9",
        operations=operations,
    )


def test_del_last_if_exact_suffix():
    assert del_last_if(
        "abc;",
        ";",
    ) == "abc"

    assert del_last_if(
        "abc;;",
        ";",
    ) == "abc;"

    assert del_last_if(
        "abc",
        ";",
    ) == "abc"


def test_del_last_if_ins_repeated_trailing_chars():
    assert del_last_if_ins(
        "abc;.)\r\n",
        ".,;)" + CRLF,
    ) == "abc"


def test_merge_text_matches_legacy_spacing():
    assert merge_text(
        "abc",
        "def",
    ) == "abc def"

    assert merge_text(
        "abc ",
        "def",
    ) == "abc def"

    assert merge_text(
        "abc",
        " def",
    ) == "abc def"


def test_split_lines_default_contract():
    assert split_lines(
        "A; B;"
    ) == (
        "A;"
        + CRLF
        + TAB
        + "B."
    )


def test_split_lines_packaging_separator():
    assert split_lines(
        "A; B;",
        "; ",
    ) == "A; B."


def test_khong_dau_uses_exact_character_map():
    assert khong_dau(
        "Đường đá Á",
        _dictionary(),
    ) == "Dường da A"


def test_translate_daychuyen_gmp_uses_words():
    assert translate_ve_daychuyen(
        "Thuốc vô trùng",
        gxp_type="GMP",
        dictionary=_dictionary(),
    ) == "Sterile Products"


def test_translate_daychuyen_glp_uses_same_dictionary_as_gmp():
    assert translate_ve_daychuyen(
        "Đóng gói",
        gxp_type="GLP",
        dictionary=_dictionary(),
    ) == "Packaging"


def test_translate_daychuyen_gsp_uses_words4():
    assert translate_ve_daychuyen(
        "Bảo quản",
        gxp_type="GSP",
        dictionary=_dictionary(),
    ) == "Storage"


def test_translate_daychuyen_replacement_is_case_insensitive():
    assert translate_ve_daychuyen(
        "THUỐC VÔ TRÙNG",
        gxp_type="GMP",
        dictionary=_dictionary(),
    ) == "Sterile Products"


def test_translate_daychuyen_rejects_gdp():
    with pytest.raises(
        CertificateDetailTypeTextError,
        match="Unsupported",
    ):
        translate_ve_daychuyen(
            "GDP only",
            gxp_type="GDP",
            dictionary=_dictionary(),
        )


def test_translate_diachi_prefix_dictionary_then_remainder():
    result = translate_ve_diachi(
        "Đường 12",
        dictionary=_dictionary(),
    )

    assert result == "Street 12"


def test_translate_diachi_numeric_prefix_is_preserved():
    result = translate_ve_diachi(
        "12 Đường 5",
        dictionary=_dictionary(),
    )

    assert result == "12 Street 5"


def test_translate_diachi_fallback_uses_khong_dau():
    result = translate_ve_diachi(
        "Đá",
        dictionary=_dictionary(),
    )

    assert result == "Da"


def test_translate_diachi_multiline_adds_asterisk():
    result = translate_ve_diachi(
        "Đường 1"
        + CRLF
        + "Phường 2",
        dictionary=_dictionary(),
    )

    assert result.startswith("* ")
    assert CRLF + "* " in result


def test_resolver_heading_pair():
    projection = _projection(
        [
            _op(
                1,
                "scope_heading_vi",
                "Đường 12¶",
            ),
            _op(
                2,
                "scope_heading_en",
                "Đường 12¶",
            ),
        ]
    )

    resolved = resolve_certificate_detail_typetext(
        projection,
        dictionary=_dictionary(),
    )

    assert resolved[1] == "* Đường 12 - "
    assert resolved[2] == "Street 12" + CRLF


def test_resolver_main_topic_vi_and_en():
    projection = _projection(
        [
            _op(
                1,
                "append_custom_description_vi",
                "Thuốc vô trùng;",
                "main_topic",
            ),
            _op(
                2,
                "append_custom_description_en",
                "Thuốc vô trùng;",
                "main_topic",
            ),
        ]
    )

    resolved = resolve_certificate_detail_typetext(
        projection,
        dictionary=_dictionary(),
    )

    assert resolved[1] == " (Thuốc vô trùng)"
    assert resolved[2] == " (Sterile Products)"


def test_resolver_packaging_vi_and_en():
    projection = _projection(
        [
            _op(
                1,
                "append_custom_description_vi",
                "Thuốc vô trùng; Đóng gói;",
                "packaging_special",
            ),
            _op(
                2,
                "append_custom_description_en",
                "Thuốc vô trùng; Đóng gói;",
                "packaging_special",
            ),
        ]
    )

    resolved = resolve_certificate_detail_typetext(
        projection,
        dictionary=_dictionary(),
    )

    assert resolved[1] == (
        ":"
        + CRLF
        + TAB
        + "Thuốc vô trùng; Đóng gói."
    )

    assert resolved[2] == (
        ":"
        + CRLF
        + TAB
        + "Sterile Products; Packaging."
    )


def test_resolver_normal_description_uses_default_splitlines():
    projection = _projection(
        [
            _op(
                1,
                "append_custom_description_vi",
                "A; B;",
                "normal",
            ),
        ]
    )

    resolved = resolve_certificate_detail_typetext(
        projection,
        dictionary=_dictionary(),
    )

    assert resolved[1] == (
        ":"
        + CRLF
        + TAB
        + "A;"
        + CRLF
        + TAB
        + "B."
    )


def test_resolver_note_en_is_double_translation():
    dictionary = CertificateDetailTranslationDictionary(
        acchs="Đ",
        rgchs="D",
        matrices={
            "TV_Words": (
                ("A",),
                ("B",),
            ),
            "TA_Words": (
                ("B",),
                ("C",),
            ),
            "TV_Words2": (("",),),
            "TA_Words2": (("",),),
            "TA_Words2_Loc": (("", ""),),
            "TV_Words4": (("",),),
            "TA_Words4": (("",),),
            "TV_Words6": (("",),),
            "TA_Words6": (("",),),
        },
    )

    projection = _projection(
        [
            _op(
                1,
                "append_scope_note_en",
                "A",
            ),
        ]
    )

    resolved = resolve_certificate_detail_typetext(
        projection,
        dictionary=dictionary,
    )

    #
    # Legacy explicitly executes Translate twice.
    #
    assert resolved[1] == TAB + "C" + CRLF


def test_resolver_fragment_copy_has_no_typetext_payload():
    projection = _projection(
        [
            _op(
                1,
                "formatted_fragment_copy",
            ),
        ]
    )

    assert resolve_certificate_detail_typetext(
        projection,
        dictionary=_dictionary(),
    ) == {}


def test_resolver_rejects_gdp():
    projection = _projection(
        [],
        gxp_type="GDP",
    )

    with pytest.raises(
        CertificateDetailTypeTextError,
        match="Unsupported",
    ):
        resolve_certificate_detail_typetext(
            projection,
            dictionary=_dictionary(),
        )


def test_resolver_rejects_unknown_operation():
    projection = _projection(
        [
            _op(
                1,
                "unknown_operation",
            ),
        ]
    )

    with pytest.raises(
        CertificateDetailTypeTextError,
        match="Unsupported",
    ):
        resolve_certificate_detail_typetext(
            projection,
            dictionary=_dictionary(),
        )