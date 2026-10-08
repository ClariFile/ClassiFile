"""Synthetic DOCX, PPTX and ODT packages covering reader edge cases. Content is invented.

These are hand-built XML, not files saved by Word, PowerPoint or LibreOffice; tests on real files are separate.
"""
import zipfile

import pymupdf

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


def text_png(text="Scanned Diagram Legend"):
    """A picture whose words exist only as pixels, for OCR tests."""
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=200)
    page.insert_text((30, 110), text, fontsize=36)
    return page.get_pixmap(dpi=150).tobytes("png")


IMAGE_TEXT = text_png()


def _zip(path, parts):
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return path


# -- DOCX -------------------------------------------------------------------------------------------
_WNS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')
_CORE = ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
         'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title><dc:subject>{subject}</dc:subject>'
         '</cp:coreProperties>')


def _wp(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def _txbx(text):
    return f'<wps:wsp><wps:txbx><w:txbxContent>{_wp(text)}</w:txbxContent></wps:txbx></wps:wsp>'


DOCX_BODY = (
    _wp("Database Systems Handbook", "Title")
    # Tab-stop definitions inside pPr are not text; the footnote reference adds nothing.
    + '<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:tabs><w:tab w:val="left" w:pos="720"/></w:tabs></w:pPr>'
      '<w:r><w:t>Introduction</w:t></w:r><w:r><w:footnoteReference w:id="1"/></w:r></w:p>'
    # Tracked deletion, tracked insertion and a field code.
    + '<w:p><w:r><w:rPr><w:sz w:val="32"/></w:rPr><w:t xml:space="preserve">Keep this sentence. </w:t></w:r>'
      '<w:del w:id="9" w:author="x"><w:r><w:delText>Obsolete clause.</w:delText></w:r></w:del>'
      '<w:ins w:id="10" w:author="x"><w:r><w:t>Inserted words.</w:t></w:r></w:ins>'
      '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> PAGE </w:instrText></w:r>'
      '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>7</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    # A text box in mc:AlternateContent: the VML fallback repeats it and must not be read twice.
    + '<w:p><w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><wp:anchor><wp:extent cx="900000" cy="300000"/>'
      '<a:graphic><a:graphicData>' + _txbx("Text box about normalization") + '</a:graphicData></a:graphic></wp:anchor>'
      '</w:drawing></mc:Choice><mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent>'
      + _wp("Text box about normalization") + '</w:txbxContent></v:textbox></v:shape></w:pict></mc:Fallback>'
      '</mc:AlternateContent></w:r><w:r><w:t>Anchor paragraph</w:t></w:r></w:p>'
    # Grouped shapes, each with its own text box.
    + '<w:p><w:r><w:drawing><wp:anchor><wp:extent cx="900000" cy="300000"/><a:graphic><a:graphicData><wpg:wgp>'
      + _txbx("Grouped shape one") + _txbx("Grouped shape two")
      + '</wpg:wgp></a:graphicData></a:graphic></wp:anchor></w:drawing></w:r></w:p>'
    # A table with a nested table in one cell.
    + '<w:tbl><w:tblPr/><w:tr><w:tc>' + _wp("Cell A1") + '</w:tc><w:tc>' + _wp("Cell B1")
      + '<w:tbl><w:tr><w:tc>' + _wp("Nested cell") + '</w:tc></w:tr></w:tbl><w:p/></w:tc></w:tr>'
      '<w:tr><w:tc>' + _wp("Cell A2") + '</w:tc><w:tc>' + _wp("Cell B2") + '</w:tc></w:tr></w:tbl>'
    # Explicit page break in an otherwise empty paragraph.
    + '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
    # A large picture with no native text: about 34% of a Letter page.
    + '<w:p><w:r><w:drawing><wp:inline><wp:extent cx="6000000" cy="4500000"/><a:graphic><a:graphicData><pic:pic>'
      '<pic:blipFill><a:blip r:embed="rId9"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></wp:inline>'
      '</w:drawing></w:r></w:p>'
    + '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:lastRenderedPageBreak/><w:t>Second Chapter</w:t></w:r></w:p>'
    + '<w:sdt><w:sdtContent>' + _wp("Content control text") + '</w:sdtContent></w:sdt>'
    # An Office Math equation: E = m c squared.
    + '<w:p><w:r><w:t xml:space="preserve">Energy: </w:t></w:r><m:oMath><m:r><m:t>E=m</m:t></m:r><m:sSup><m:e>'
      '<m:r><m:t>c</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:oMath></w:p>'
    + '<w:sectPr><w:headerReference w:type="default" r:id="rId1"/><w:pgSz w:w="12240" w:h="15840"/></w:sectPr>'
)


def make_docx(path, body=DOCX_BODY, image=IMAGE_TEXT):
    return _zip(path, {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        "word/document.xml": f'<w:document {_WNS}><w:body>{body}</w:body></w:document>',
        "word/styles.xml": f'<w:styles {_WNS}><w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="22"/></w:rPr>'
                           '</w:rPrDefault></w:docDefaults>'
                           '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
                           '<w:rPr><w:sz w:val="56"/></w:rPr></w:style>'
                           '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
                           '<w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style></w:styles>',
        "word/header1.xml": f'<w:hdr {_WNS}>' + _wp("Database Systems Handbook - running header") + '</w:hdr>',
        "word/footer1.xml": f'<w:ftr {_WNS}>' + _wp("Course DBS-2041 footer") + '</w:ftr>',
        "word/footnotes.xml": f'<w:footnotes {_WNS}><w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/>'
                              '</w:r></w:p></w:footnote><w:footnote w:id="1">' + _wp("Footnote about normal forms.")
                              + '</w:footnote></w:footnotes>',
        "word/comments.xml": f'<w:comments {_WNS}><w:comment w:id="0">' + _wp("Reviewer comment") + '</w:comment></w:comments>',
        "word/_rels/document.xml.rels": _rels(("rId1", "header", "header1.xml"), ("rId9", "image", "media/image1.png")),
        "word/media/image1.png": image,
        "docProps/core.xml": _CORE.format(title="Database Systems Handbook", subject="Databases"),
    })


# -- PPTX -------------------------------------------------------------------------------------------
_PNS = ('xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" '
        'xmlns:a14="http://schemas.microsoft.com/office/drawing/2010/main" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')
_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"


def _rels(*rels):
    body = "".join(f'<Relationship Id="{i}" Type="{_RT}{t}" Target="{target}"/>' for i, t, target in rels)
    return f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{body}</Relationships>'


def _xfrm(cx, cy, tag="a:xfrm"):
    return f'<{tag}><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></{tag}>'


def _sp(text, ph=None, cx=None, cy=None, sz=None):
    nv = f'<p:nvPr><p:ph type="{ph}"/></p:nvPr>' if ph else "<p:nvPr/>"
    rpr = f'<a:rPr sz="{sz}"/>' if sz else ""
    paras = "".join(f"<a:p><a:r>{rpr}<a:t>{t}</a:t></a:r></a:p>" for t in text.split("\n"))
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="1" name="s"/><p:cNvSpPr/>{nv}</p:nvSpPr>'
            f'<p:spPr>{_xfrm(cx, cy) if cx else ""}</p:spPr><p:txBody><a:bodyPr/>{paras}</p:txBody></p:sp>')


def _pic(rid, cx, cy):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="2" name="p"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/></p:blipFill><p:spPr>{_xfrm(cx, cy)}</p:spPr></p:pic>')


def _slide(shapes, show=True):
    attr = "" if show else ' show="0"'
    return f'<p:sld {_PNS}{attr}><p:cSld><p:spTree>{shapes}</p:spTree></p:cSld></p:sld>'


FOOTER = _sp("NSF course footer", "ftr", 3000000, 300000)
BACKGROUND = _pic("rIdBg", 9144000, 6858000)  # same image part on 3 of 4 slides: repeated


def make_pptx(path):
    slide2 = (
        _sp("Firewalls", "title", sz=4400) + _sp("Packet filtering\nStateful inspection", "body")
        + '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="3" name="t"/><p:cNvGraphicFramePr/><p:nvPr/>'
          '</p:nvGraphicFramePr>' + _xfrm(4000000, 1000000, "p:xfrm") + '<a:graphic><a:graphicData><a:tbl>'
          '<a:tr><a:tc><a:txBody><a:p><a:r><a:t>Rule table cell one</a:t></a:r></a:p></a:txBody></a:tc>'
          '<a:tc><a:txBody><a:p><a:r><a:t>Allow</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl>'
          '</a:graphicData></a:graphic></p:graphicFrame>'
        + '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="4" name="g"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>'
          '<a:off x="0" y="0"/><a:ext cx="2000000" cy="500000"/><a:chOff x="0" y="0"/><a:chExt cx="4000000" cy="1000000"/>'
          '</a:xfrm></p:grpSpPr>' + _sp("Grouped label one", None, 2000000, 1000000)
        + _sp("Grouped label two", None, 2000000, 1000000) + '</p:grpSp>'
        + '<mc:AlternateContent><mc:Choice Requires="p14">' + _sp("Alternate content text")
        + '</mc:Choice><mc:Fallback>' + _sp("Alternate content text") + '</mc:Fallback></mc:AlternateContent>'
        + '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="5" name="d"/><p:cNvGraphicFramePr/><p:nvPr/>'
          '</p:nvGraphicFramePr>' + _xfrm(1000000, 1000000, "p:xfrm") + '<a:graphic><a:graphicData>'
          '<dgm:relIds r:dm="rIdDm"/></a:graphicData></a:graphic></p:graphicFrame>'
        # An equation: PowerPoint keeps the math in mc:Choice and a picture of it in mc:Fallback.
        + '<mc:AlternateContent><mc:Choice Requires="a14"><p:sp><p:nvSpPr><p:cNvPr id="6" name="e"/><p:cNvSpPr/>'
          '<p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:p><a14:m><m:oMathPara><m:oMath><m:r><m:t>x=y+1</m:t>'
          '</m:r></m:oMath></m:oMathPara></a14:m></a:p></p:txBody></p:sp></mc:Choice><mc:Fallback>'
        + _pic("rIdBg", 100, 100) + '</mc:Fallback></mc:AlternateContent>'
        + FOOTER + BACKGROUND
    )
    notes = (f'<p:notes {_PNS}><p:cSld><p:spTree>' + _sp("", "sldImg")
             + _sp("Speaker note: explain stateful inspection", "body") + _sp("2", "sldNum") + '</p:spTree></p:cSld></p:notes>')
    slide_rels = ("rIdL", "slideLayout", "../slideLayouts/slideLayout1.xml"), ("rIdBg", "image", "../media/bg.png")
    return _zip(path, {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        "ppt/presentation.xml": f'<p:presentation {_PNS}><p:sldIdLst><p:sldId id="256" r:id="rId2"/>'
                                '<p:sldId id="257" r:id="rId3"/><p:sldId id="258" r:id="rId4"/><p:sldId id="259" r:id="rId5"/>'
                                '</p:sldIdLst><p:sldSz cx="9144000" cy="6858000"/></p:presentation>',
        "ppt/_rels/presentation.xml.rels": _rels(("rId2", "slide", "slides/slide1.xml"), ("rId3", "slide", "slides/slide2.xml"),
                                                 ("rId4", "slide", "slides/slide3.xml"), ("rId5", "slide", "slides/slide4.xml")),
        "ppt/slides/slide1.xml": _slide(_sp("Network Security Fundamentals", "ctrTitle") + _sp("Lecture 3", "subTitle")
                                        + FOOTER + BACKGROUND),
        "ppt/slides/_rels/slide1.xml.rels": _rels(*slide_rels),
        "ppt/slides/slide2.xml": _slide(slide2),
        "ppt/slides/_rels/slide2.xml.rels": _rels(*slide_rels, ("rIdN", "notesSlide", "../notesSlides/notesSlide2.xml"),
                                                  ("rIdDm", "diagramData", "../diagrams/data1.xml")),
        "ppt/notesSlides/notesSlide2.xml": notes,
        "ppt/diagrams/data1.xml": f'<dgm:dataModel {_PNS}><dgm:ptLst><dgm:pt modelId="1"><dgm:t><a:bodyPr/><a:p><a:r>'
                                  '<a:t>SmartArt step one</a:t></a:r></a:p></dgm:t></dgm:pt></dgm:ptLst></dgm:dataModel>',
        "ppt/slides/slide3.xml": _slide(_pic("rIdImg", 6000000, 4500000) + FOOTER),
        "ppt/slides/_rels/slide3.xml.rels": _rels(slide_rels[0], ("rIdImg", "image", "../media/image1.png")),
        "ppt/slides/slide4.xml": _slide(_sp("Backup slide", "title") + BACKGROUND, show=False),
        "ppt/slides/_rels/slide4.xml.rels": _rels(*slide_rels),
        "ppt/slideLayouts/slideLayout1.xml": f'<p:sldLayout {_PNS}><p:cSld><p:spTree>'
                                             + _sp("Click to edit Master title style", "title") + _sp("Layout brand text")
                                             + '</p:spTree></p:cSld></p:sldLayout>',
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": _rels(("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")),
        "ppt/slideMasters/slideMaster1.xml": f'<p:sldMaster {_PNS}><p:cSld><p:spTree>' + _sp("Click to edit Master text styles", "body")
                                             + _sp("Network Security Fundamentals master text") + '</p:spTree></p:cSld></p:sldMaster>',
        "ppt/media/bg.png": PNG, "ppt/media/image1.png": IMAGE_TEXT,
        "docProps/core.xml": _CORE.format(title="PowerPoint Presentation", subject=""),
    })


# -- ODT --------------------------------------------------------------------------------------------
_ONS = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
        'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
        'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
        'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"')

ODT_BODY = (
    '<text:tracked-changes><text:changed-region text:id="c1"><text:deletion><text:p>Obsolete clause.</text:p>'
    '</text:deletion></text:changed-region></text:tracked-changes><text:sequence-decls/>'
    '<text:h text:outline-level="1" text:style-name="P2">Database Systems Handbook</text:h>'
    '<text:p>Keep this<text:s text:c="2"/>sentence.<text:tab/>Tabbed<text:note text:note-class="footnote">'
    '<text:note-citation>1</text:note-citation><text:note-body><text:p>Footnote about normal forms.</text:p>'
    '</text:note-body></text:note> after note.<office:annotation><text:p>Reviewer comment</text:p></office:annotation>'
    '<text:change text:change-id="c1"/><text:span>Spanned</text:span> end.</text:p>'
    '<text:p><draw:frame svg:width="2in" svg:height="1in"><draw:text-box><text:p>Text box about normalization</text:p>'
    '</draw:text-box></draw:frame>Anchor paragraph</text:p>'
    '<text:p><draw:g><draw:custom-shape><text:p>Grouped shape one</text:p></draw:custom-shape>'
    '<draw:custom-shape><text:p>Grouped shape two</text:p></draw:custom-shape></draw:g></text:p>'
    '<text:list><text:list-item><text:p>First item</text:p><text:list><text:list-item><text:p>Nested item</text:p>'
    '</text:list-item></text:list></text:list-item></text:list>'
    '<table:table><table:table-header-rows><table:table-row><table:table-cell><text:p>Cell A1</text:p></table:table-cell>'
    '<table:table-cell><text:p>Cell B1</text:p></table:table-cell></table:table-row></table:table-header-rows>'
    '<table:table-row><table:table-cell><text:p>Cell A2</text:p></table:table-cell><table:table-cell>'
    '<table:table><table:table-row><table:table-cell><text:p>Nested cell</text:p></table:table-cell></table:table-row>'
    '</table:table></table:table-cell></table:table-row></table:table>'
    '<text:table-of-content><text:index-body><text:p>Contents entry</text:p></text:index-body></text:table-of-content>'
    '<text:p><draw:frame svg:width="7in" svg:height="5in"><draw:image xlink:href="Pictures/a.png"/></draw:frame></text:p>'
    '<text:soft-page-break/>'
    '<text:h text:outline-level="1">Second Chapter</text:h>'
    '<text:p text:style-name="P1">Forced page paragraph</text:p>'
    '<text:section text:name="S1"><text:p>Section text</text:p></text:section>'
)


def make_odt(path, body=ODT_BODY, mimetype="application/vnd.oasis.opendocument.text", manifest_extra=""):
    return _zip(path, {
        "mimetype": mimetype,
        "META-INF/manifest.xml": '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
                                 f'{manifest_extra}</manifest:manifest>',
        "content.xml": f'<office:document-content {_ONS}><office:automatic-styles><style:style style:name="P1" '
                       'style:family="paragraph"><style:paragraph-properties fo:break-before="page"/></style:style>'
                       '<style:style style:name="P2" style:family="paragraph" style:parent-style-name="Big"/>'
                       f'</office:automatic-styles><office:body><office:text>{body}</office:text></office:body>'
                       '</office:document-content>',
        "styles.xml": f'<office:document-styles {_ONS}><office:styles><style:default-style style:family="paragraph">'
                      '<style:text-properties fo:font-size="12pt"/></style:default-style><style:style style:name="Big" '
                      'style:family="paragraph"><style:text-properties fo:font-size="18pt"/></style:style></office:styles>'
                      '<office:automatic-styles><style:page-layout style:name="pm1">'
                      '<style:page-layout-properties fo:page-width="8.5in" fo:page-height="11in"/></style:page-layout>'
                      '</office:automatic-styles><office:master-styles><style:master-page style:name="Standard" '
                      'style:page-layout-name="pm1"><style:header><text:p>Database Systems Handbook - running header</text:p>'
                      '</style:header><style:footer><text:p>Course DBS-2041 footer</text:p></style:footer></style:master-page>'
                      '</office:master-styles></office:document-styles>',
        "meta.xml": f'<office:document-meta {_ONS}><office:meta><dc:title>Database Systems Handbook</dc:title>'
                    '<meta:keyword>databases</meta:keyword><meta:keyword>SQL</meta:keyword></office:meta></office:document-meta>',
        "Pictures/a.png": IMAGE_TEXT,
    })
