Private Sub Inc_Val(ByVal i&):    Set_Val CurVal + i:    End Sub

Private Function Get_Bookmark(ByRef wdDoc As Object, ByVal bm$) As String
    On Error Resume Next
    Get_Bookmark = wdDoc.Bookmarks(bm).Range.Text
End Function
