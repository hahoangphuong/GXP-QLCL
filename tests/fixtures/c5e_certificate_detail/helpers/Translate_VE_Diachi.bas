Public Function Translate_VE_Diachi(ByVal s$) As String
    Dim Viet As Variant, Anh As Variant, loc As Variant
    Dim i%, j%, k%, m%, rs$, Bsl As Variant, sl As Variant, vl As Variant, slk$, spe$, lc$, found As Boolean, fspe$
    '
    s = Trim(s):    If s = vbNullString Then Exit Function
    s = DelLastIf_Ins(s, ".,;)" & vbCrLf)    'If InStr(1, ".,;)" & vbCrLf, Right(s, 1), vbTextCompare) > 0 Then s = Left(s, Len(s) - 1)
    rs = Trim(s)
    If rs = vbNullString Then Exit Function
    rs = Replace(rs, "   ", " "):   rs = Replace(rs, "  ", " ")
    Viet = Names("TV_Words2").RefersToRange.Value
    Anh = Names("TA_Words2").RefersToRange.Value
    loc = Names("TA_Words2_Loc").RefersToRange.Value
    Bsl = Split(rs, vbCrLf)
    For m = LBound(Bsl) To UBound(Bsl)
        Bsl(m) = Trim(Bsl(m))
        If Left(Bsl(m), 1) = "*" Then Bsl(m) = Trim(Right(Bsl(m), Len(Bsl(m)) - 1))
        sl = Split(Bsl(m), ",")
        For k = LBound(sl) To UBound(sl)
            slk = Trim(sl(k))
            If ((Left(slk, 1) >= "0") And (Left(slk, 1) <= "9")) Then
                j = 1
                While (Mid(slk, j, 1) <> " ") And (j < Len(slk)): j = j + 1: Wend
                If j < Len(slk) Then
                    fspe = Trim(Left(slk, j - 1))
                    slk = Trim(Right(slk, Len(slk) - j))
                Else: fspe = vbNullString
                End If
            Else: fspe = vbNullString
            End If
            found = False
            For i = LBound(Viet, 1) To UBound(Viet, 1)
                If Viet(i, 1) <> "" Then
                    vl = Split(Viet(i, 1), "|")
                    For j = LBound(vl) To UBound(vl)
                        If StrComp(Left(slk, Len(vl(j))), vl(j), vbTextCompare) = 0 Then
                            spe = KhongDau(Trim(Right(slk, Len(slk) - Len(vl(j)))))
                            If ((Left(spe, 1) >= "0") And (Left(spe, 1) <= "9")) Or (Left(spe, 1) = "I") Then _
                                lc = UCase(loc(i, 2)) Else lc = UCase(loc(i, 1))
                            If lc = "T" Then
                                sl(k) = Merge_Text(Anh(i, 1), spe)
                            Else
                                sl(k) = Merge_Text(spe, Anh(i, 1))
                            End If
                            If fspe <> vbNullString Then sl(k) = Merge_Text(fspe, sl(k))
                            found = True
                            Exit For
                        End If
                    Next j
                End If
                If found Then Exit For
            Next i
            If Not found Then
                sl(k) = KhongDau(Trim(slk))
                If fspe <> vbNullString Then sl(k) = Merge_Text(fspe, sl(k))
            End If
        Next k
        If UBound(Bsl) > LBound(Bsl) Then Bsl(m) = Merge_Text("*", Join(sl, ", ")) Else Bsl(m) = Join(sl, ", ")
    Next m
    rs = Join(Bsl, vbCrLf)
    rs = Replace(rs, "   ", " "):   rs = Replace(rs, "  ", " ")
    Translate_VE_Diachi = Trim(rs)
End Function
