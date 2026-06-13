#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
#*********************************************************************************************************
#*   __     __               __     ______                __   __                      _______ _______   *
#*  |  |--.|  |.---.-..----.|  |--.|   __ \.---.-..-----.|  |_|  |--..-----..----.    |       |     __|  *
#*  |  _  ||  ||  _  ||  __||    < |    __/|  _  ||     ||   _|     ||  -__||   _|    |   -   |__     |  *
#*  |_____||__||___._||____||__|__||___|   |___._||__|__||____|__|__||_____||__|      |_______|_______|  *
#*http://www.blackpantheros.eu | http://www.blackpanther.hu - kbarcza[]blackpanther.hu * Charles K Barcza*
#*************************************************************************************(c)2002-2019********

import os, sys, time

def update_messages():
    pkgname="pycoderai"
    os.system("rm -rf .tmp")
    os.makedirs(".tmp")
    os.system("mkdir -p po")
    os.system("""find . -type f -name '*.py' -print |xargs \
     xgettext --default-domain=%s --keyword=_ --keyword=i18n --keyword=ki18n \
              --package-name='PyCoderAi' \
              --package-version=0.9.4 \
              --copyright-holder='blackPanther Europe' \
              --msgid-bugs-address=info@blackpantheros.eu \
              -o po/tmp.pot *.py""" % (pkgname))
    print("Scan done!")
    time.sleep(3)
    os.system("msgcat --use-first po/tmp.pot >po/%s.pot" % (pkgname))
    os.system("rm po/tmp.pot")

    locale_dir = "locales"

    for item in os.listdir("po"):
        if item.endswith(".po"):
            os.system("msgmerge -q -o .tmp/temp.po po/%s po/%s.pot" % (item, pkgname))
            os.system("cp .tmp/temp.po po/%s" % item)

            print ("Build locales...")

            filename = item
            lang = filename.rsplit(".", 1)[0]

            try:
                #print(os.path.join(locale_dir, "%s/LC_MESSAGES" % lang))
                os.makedirs(os.path.join(locale_dir, "%s/LC_MESSAGES" % lang))
            except OSError:
                pass

            os.system("msgfmt po/%s.po -o locales/%s/LC_MESSAGES/%s.mo" % (lang, lang, pkgname))

    os.system("rm -rf .tmp")
    print ("All locales are updated!")


import cx_Freeze
import tempfile
def run_setup():
    tdir = tempfile.mkdtemp()
    scriptfile = os.path.join(tdir,"script.py")
    distdir = distdir = os.path.join(tdir,"dist")
    with open(scriptfile,"w") as f:
        f.write("import signedimp.crypto.rsa\n")
    f = cx_Freeze.Freezer([cx_Freeze.Executable(scriptfile)]) #,
                          #targetDir=distdir)
    f.freeze()
    if sys.platform == "win32":
        self.scriptexe = os.path.join(self.distdir,"script.exe")
    else:
        self.scriptexe = os.path.join(distdir,"script")


if __name__ == "__main__":
    # Translation maintenance script (xgettext / msgfmt for i18n).
    # This used to run unconditionally at import time + sys.exit(0) which
    # broke any packaging, pip install, or `python -c "import ..."` that touched setup.py.
    # Now guarded: run `python setup.py` (or `python -m setup`) to update locales.
    update_messages()
    print("Translations is updated!")
    # run_setup()  # was broken anyway (self refs outside class)
    sys.exit(0)
else:
    # When imported as module (by setuptools, pip, etc.) do nothing.
    pass

