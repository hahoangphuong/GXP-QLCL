Private Function Key2Bookmark(ByVal s$) As String
    '
    s = Trim$(s)
    If Right$(s, 1) = "." Then s = Left$(s, Len(s) - 1)
    Key2Bookmark = "L" & Replace(s, ".", "_", 1, -1, vbTextCompare)
End Function
