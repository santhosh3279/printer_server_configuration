[33mcommit 88f108246d94a1a6632a718bb62c48015c309823[m[33m ([m[1;36mHEAD[m[33m -> [m[1;32mversion-16[m[33m, [m[1;31morigin/version-16[m[33m)[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat May 23 14:35:14 2026 +0000

    done

[33mcommit 4a7b61e8e656ae1f35d23b0c11e0a8e6a3f945f6[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Fri May 22 13:56:09 2026 +0000

    barcode

[33mcommit 01cb59e43c4abdb120ed1996f3e1d3f3dfe98141[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sun Apr 19 17:24:44 2026 +0000

    fix: remove fetch_from stock_uom on item_uom in Barcode_subwindow to allow custom UOM selection

[33mcommit 13b90a8c890875e82c1483d9d633b3dfb0d9338a[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sun Apr 12 17:30:43 2026 +0000

    Added Reprot Format

[33mcommit daecb0bb57c78eb13c830a7332f4261b30f9e6ff[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Wed Apr 1 06:28:37 2026 +0000

    Custom PDF Fixed error

[33mcommit af3ba90460adb36c46f8a056eb0f4da8fc5d9209[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Tue Mar 31 19:05:52 2026 +0000

    added pytohon

[33mcommit b32be6f88d30be4ce9dfb2dd4428ad76b2556187[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Tue Mar 31 13:32:39 2026 +0000

    added default templates

[33mcommit 6f7b6fdac714507b3cf4d6f6d8cb013638becd2d[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 12:31:22 2026 +0000

    Fix A5 wkhtmltopdf error: use page-size A5 instead of Custom
    
    Unpatched wkhtmltopdf 0.12.6 rejects --page-size Custom.
    Use the standard A5 page size with orientation flag instead;
    pypdf post-processing still places each page on A4.
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit 7b81db6a9f1180caf289fa06ebf1b215b9c472f6[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 12:22:04 2026 +0000

    A5 pagination: use native page size + pypdf post-processing onto A4
    
    Instead of CSS transform (which blocks overflow), wkhtmltopdf now
    renders into the actual A5 dimensions so it paginates automatically:
      Landscape: page-width=210mm, page-height=148.5mm
      Portrait:  page-width=148mm, page-height=210mm
    
    Each resulting A5 page is then placed onto the top half of an A4 sheet
    via pypdf (_place_a5_on_a4):
      Landscape: translate to top of A4, no rotation
      Portrait:  rotate 90° CCW then translate to top of A4
                 (top edge → left of A4, bottom edge → right of A4)
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit ded9c3a9890b68cd43ca83032e20d3185be1c23b[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 10:25:56 2026 +0000

    Preserve user-defined header/footer margins in A5-on-A4 Custom PDF
    
    Only inject empty marker divs when the template has no existing
    id="header-html" or id="footer-html" elements, so user-set margins
    from the doctype entry are not suppressed.
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit 3c93167a0387893e8d9b8c81c8f518f92ace7f29[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 10:17:47 2026 +0000

    Fix top/bottom 15mm margins on A5-on-A4 by suppressing frappe's header/footer defaults
    
    frappe's prepare_header_footer unconditionally sets margin-top/bottom to
    15mm when no header/footer element is found, overriding our 0mm options.
    Inject empty marker divs so frappe takes the file-creation branch instead.
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit eac8be21de371e693b336df6d2c8b01bc4741570[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 10:13:50 2026 +0000

    Pass explicit zero margins to wkhtmltopdf for A5-on-A4 Custom PDF
    
    Frappe defaults margin-left/right to 15mm when not set; override all
    four margins to 0mm so the A4 page has no padding around the A5 content.
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit 73c0b0f4adb99a31ccf581a78bf136c19958f506[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 10:11:21 2026 +0000

    Remove A4 page margin for A5 print via @page margin:0
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit d0118b164299df8fb5b621482f916b3a617711e3[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 09:56:17 2026 +0000

    Remove hardcoded margins and borders from Custom PDF A5 injected CSS
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit 2e1bd378cc6f85c19ee434faa846248e901e7052[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 09:18:38 2026 +0000

    A5 on A4: portrait rotates content -90°, landscape fills top half flat
    
    Portrait: wraps body in .a5-wrap with transform:translateY(148mm) rotate(-90deg)
      → content top edge appears at left of A4, bottom edge at right of A4
    Landscape: constrains body to 210×148mm (top half of A4 portrait), no rotation
      → content top = top of page, bottom = middle of page
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit 3725f827f43e70dc874d71932cf2c8599cfdfdbd[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 09:09:09 2026 +0000

    Print A5 on top half of A4 sheet in Custom PDF format
    
    When page size is A5, generate an A4 PDF with CSS constraining
    content to the top 148mm so no paper change is needed on the printer.
    All other page sizes use their native dimensions as before.
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit 07a1bb12ac78319fe2f265e46102d7d9a4ecef70[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 09:07:00 2026 +0000

    Revert "Fix landscape orientation for Custom PDF via CSS @page injection"
    
    This reverts commit 0e56156c7abd4b29de0959c1b2e1a82b227fed02.

[33mcommit 0e56156c7abd4b29de0959c1b2e1a82b227fed02[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 09:04:45 2026 +0000

    Fix landscape orientation for Custom PDF via CSS @page injection
    
    Inject a CSS @page{size:...} rule into the HTML so wkhtmltopdf
    reliably renders portrait/landscape — passing only the orientation
    option was insufficient for some printers.
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit e004addb8ecf124c6697967996fef3418cc9b5fe[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 07:43:14 2026 +0000

    Add Custom PDF reference section to Print Template help
    
    Adds a documentation block in the Reference section covering Custom PDF:
    available Jinja variables, filters, and a full HTML template example.
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit d3d858cfd24be7ac7ad94934206cf37f40a9cd7b[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Sat Mar 28 07:17:01 2026 +0000

    Add Custom PDF format type to Print Template
    
    Adds a new "Custom PDF" format option that renders a custom Jinja HTML
    template to PDF with configurable page size and orientation, and an
    optional Letter Head — independent of ERPNext Print Format.
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit a41061c037db86e7d7db652ec3a67ecb14211cf6[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Tue Mar 24 07:58:27 2026 +0000

    Add barcode doctypes and enhance print template rendering
    
    - Added barcode_prinitng and barcode_subwindow doctypes
    - Updated print_template doctype with new fields and rendering logic
    - Enhanced render_utils.py with additional rendering capabilities
    - Updated fixtures and hooks
    
    Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

[33mcommit 7b376367ebeb32c8094d2ef70081999dde29b8ca[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Fri Mar 13 14:12:32 2026 +0000

    Print Format Fixed

[33mcommit bdafc09c7b9f8f8b2ab8909d43001ed5a581c3bc[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Fri Mar 13 14:01:16 2026 +0000

    Print Format Fixed

[33mcommit 25b1c59ce48356b85d6af21480e7a4fea105df0c[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Fri Mar 13 13:53:36 2026 +0000

    Print Format Fixed

[33mcommit 51eea119ca86bbb0a75d45f9ef09ffa8af07f929[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Wed Mar 11 18:46:39 2026 +0000

    Printer Templates

[33mcommit 12e693e88d4f6b063722ea3950557937ee8163fb[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Wed Mar 11 16:35:18 2026 +0000

    Working

[33mcommit d3d8f71b0b6a6f54de61d6e119f9e112bb81c26f[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Tue Mar 10 13:49:59 2026 +0000

    more setup

[33mcommit 1ff8b1bc949c8ec6e0afede193fca6372c716d2f[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Fri Mar 6 16:58:54 2026 +0000

    Initial App commit

[33mcommit 77047f19df7d6b035240444a1b1c9f39db02c51f[m
Author: santhosh3279 <santhosh.sundaran007@gmail.com>
Date:   Fri Mar 6 15:11:28 2026 +0000

    feat: Initialize App
