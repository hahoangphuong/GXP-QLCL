Public Function Translate_VE_Daychuyen(ByVal s$, ByVal Sel%) As String
    Dim Viet As Variant, Anh As Variant, i%, j%, rs$, vl As Variant
    '
    rs = Trim(s):    If rs = vbNullString Then Exit Function
    rs = Replace(rs, "   ", " "):   rs = Replace(rs, "  ", " ")
    If (Sel = 1) Or (Sel = 2) Then
        Viet = Names("TV_Words").RefersToRange.Value:        Anh = Names("TA_Words").RefersToRange.Value
    ElseIf Sel = 3 Then
        Viet = Names("TV_Words4").RefersToRange.Value:        Anh = Names("TA_Words4").RefersToRange.Value
'    ElseIf Sel = 2 Then
'        Viet = Names("TV_Words5").RefersToRange.Value:        Anh = Names("TA_Words5").RefersToRange.Value
    ElseIf Sel = 4 Then
        Viet = Names("TV_Words6").RefersToRange.Value:        Anh = Names("TA_Words6").RefersToRange.Value
    End If
    For i = LBound(Viet, 1) To UBound(Viet, 1)
        If Viet(i, 1) <> vbNullString Then
            vl = Split(Viet(i, 1), "|")
            For j = LBound(vl) To UBound(vl)
                rs = Replace(rs, vl(j), Anh(i, 1), 1, -1, vbTextCompare)
            Next j
        End If
    Next i
    rs = Replace(rs, "   ", " "):   rs = Replace(rs, "  ", " ")
    Translate_VE_Daychuyen = Trim(rs)
End Function
