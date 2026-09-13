Private Function SplitLines$(ByVal s$, Optional ByVal sp$ = ";" & vbCrLf & vbTab)
    Dim ss$
    '
    ss = DelLastIf(DelLastIf(DelLastIf(DelLastIf(s, vbCrLf), vbCr), vbLf), ";")
    ss = Replace(Replace(Replace(ss, "  ", " "), "  ", " "), "; ", ";")
    ss = DelLastIf(DelLastIf(DelLastIf(DelLastIf(ss, vbCrLf), vbCr), vbLf), ";")
    ss = DelLastIf(ss, ";")
    ss = Replace(ss, ";", sp)
    SplitLines = DelLastIf(ss, ".") & "."
End Function
