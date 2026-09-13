Private Function Input_DC_to_CC(ByRef wdDoc As Object, ByRef wdDoc2 As Object, ByVal DC_All$, ByVal EngPart As Boolean, Optional ByVal GPs_T$ = vbNullString) As Boolean
    Dim i&, j&, k&, PV_Desc$(), PV_map&(), ncount&, iDaychuyen$(), DC_Count&, s_N$, s_D$, s_Note$, s_Comp$
    '
    On Error Resume Next
    Input_DC_to_CC = False
    iDaychuyen = Split(DC_All, "§")
    DC_Count = UBound(iDaychuyen) - LBound(iDaychuyen) + 1
    With wdDoc
    .Bookmarks("Pvi" & GPs_T).Range.Select
    For i = 1 To DC_Count
        Call DCForm.Get_DC_Name_Desc(iDaychuyen(i - 1), s_N, s_D, s_Note, s_Comp)
        If Not DCForm.Load_DC_Nodes(s_D, PV_map, PV_Desc, ncount) Then MsgBox "Loi khi khoi tao cay pham vi chung nhan " & i: GoTo Quit0
        Inc_Val (15)
        If s_N <> vbNullString Then
            .ActiveWindow.Selection.Font.Bold = True:            .ActiveWindow.Selection.Font.Italic = False
            .ActiveWindow.Selection.ParagraphFormat.SpaceBefore = 12
            .ActiveWindow.Selection.ParagraphFormat.SpaceAfter = 3
            .ActiveWindow.Selection.TypeText Text:="* " & DelLastIf(s_N, "¶") & " - "
            .ActiveWindow.Selection.Font.Bold = True:            .ActiveWindow.Selection.Font.Italic = True
            .ActiveWindow.Selection.TypeText Text:=Translate_VE_Diachi(DelLastIf(s_N, "¶")) & vbCrLf
        End If
        For j = LBound(DCForm.PVCN_GxP, 1) To UBound(DCForm.PVCN_GxP, 1)
            Inc_Val (1)
            If PV_map(j) <> 0 Then
                .ActiveWindow.Selection.FormattedText = wdDoc2.Bookmarks(Key2Bookmark(DCForm.PVCN_GxP(j, PVCN_colKey))).Range.FormattedText
                If Trim$(PV_Desc(PV_map(j))) <> vbNullString Then
                    .ActiveWindow.Selection.EndKey Unit:=5      'wdLine
                    .ActiveWindow.Selection.Font.Color = 12611584     ' wdColorBlue
                    .ActiveWindow.Selection.Font.Bold = False
                    .ActiveWindow.Selection.Font.Italic = False
                    If (DCForm.PVCN_GxP(j, PVCN_colMainTopic) <> vbNullString) Then
                        .ActiveWindow.Selection.TypeText Text:=" (" & DelLastIf(PV_Desc(PV_map(j)), ";") & ")"
                    ElseIf (j = PVCN_rowPriPack) Or (j = PVCN_rowSecPack) Then
                        .ActiveWindow.Selection.TypeText Text:=":" & vbCrLf & vbTab & SplitLines(PV_Desc(PV_map(j)), "; ")
                    Else
                        .ActiveWindow.Selection.TypeText Text:=":" & vbCrLf & vbTab & SplitLines(PV_Desc(PV_map(j)))
                    End If
                    If EngPart Then
                        .ActiveWindow.Selection.MoveRight Unit:=12, count:=2   ' wdcell
                        .ActiveWindow.Selection.MoveRight Unit:=1, count:=1    ' wdCharacter
                        .ActiveWindow.Selection.Font.Color = 12611584     ' wdColorBlue
                        .ActiveWindow.Selection.Font.Bold = False
                        .ActiveWindow.Selection.Font.Italic = False
                        If (DCForm.PVCN_GxP(j, PVCN_colMainTopic) <> vbNullString) Then
                            .ActiveWindow.Selection.TypeText Text:=" (" & Translate_VE_Daychuyen(DelLastIf(PV_Desc(PV_map(j)), ";"), Sel_GPs) & ")"
                        ElseIf (j = PVCN_rowPriPack) Or (j = PVCN_rowSecPack) Then
                            .ActiveWindow.Selection.TypeText Text:=":" & vbCrLf & vbTab & SplitLines(Translate_VE_Daychuyen(PV_Desc(PV_map(j)), Sel_GPs), "; ")
                        Else
                            .ActiveWindow.Selection.TypeText Text:=":" & vbCrLf & vbTab & SplitLines(Translate_VE_Daychuyen(PV_Desc(PV_map(j)), Sel_GPs))
                        End If
                    End If
                    .ActiveWindow.Selection.MoveRight Unit:=1, count:=2    ' wdCharacter
                Else
                    .ActiveWindow.Selection.EndKey Unit:=5      'wdLine
                    If EngPart Then
                        .ActiveWindow.Selection.MoveRight Unit:=12, count:=2   ' wdcell
                        .ActiveWindow.Selection.MoveRight Unit:=1, count:=1    ' wdCharacter
                    End If
                    .ActiveWindow.Selection.MoveRight Unit:=1, count:=2    ' wdCharacter
                End If
            End If
        Next j
        If s_Note <> vbNullString Then
            .ActiveWindow.Selection.Font.Bold = False:            .ActiveWindow.Selection.Font.Italic = False
            .ActiveWindow.Selection.ParagraphFormat.SpaceBefore = 3
            .ActiveWindow.Selection.TypeText Text:=vbTab & s_Note & vbCrLf
            .ActiveWindow.Selection.Font.Bold = False:            .ActiveWindow.Selection.Font.Italic = True
            .ActiveWindow.Selection.TypeText Text:=vbTab & Translate_VE_Daychuyen(Translate_VE_Daychuyen(s_Note, Sel_GPs), Sel_GPs) & vbCrLf
            .ActiveWindow.Selection.ParagraphFormat.SpaceBefore = 9
            .ActiveWindow.Selection.ParagraphFormat.SpaceAfter = 0
        End If
    Next i
    End With
    Input_DC_to_CC = True
Quit0:
End Function
