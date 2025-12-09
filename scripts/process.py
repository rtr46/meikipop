#!python
# copied from see https://github.com/wareya/nazeka/blob/master/etc/process.py
from lxml import etree
from collections import OrderedDict
import json
from io import open

entries = []

XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'

# whether to only output english definitions - if so, glosses are just the gloss text, not a dictionary
eng_only = True

parser = etree.XMLParser(resolve_entities=False)
root = etree.parse("JMdict", parser);
for ent in root.iter(etree.Entity):
    if ent.getparent() is not None:
        if not ent.getparent().text:
            ent.getparent().text = ""
        if ent.text:
            ent.getparent().text += ent.text
        if ent.tail:
            ent.getparent().text += ent.tail
root = root.getroot();
for entry in root.iter("entry"):
    myentry = OrderedDict()
    seq = int(entry.find("ent_seq").text)
    k_eles = []
    for k_ele in entry.iter("k_ele"):
        keb = k_ele.find("keb").text
        ke_infs = []
        for ke_inf in k_ele.iter("ke_inf"):
            ke_infs += [ke_inf.text]
        ke_pris = []
        for ke_pri in k_ele.iter("ke_pri"):
            ke_pris += [ke_pri.text]
        element = OrderedDict()
        element["keb"] = keb
        if(len(ke_infs) > 0): element["inf"] = ke_infs
        if(len(ke_pris) > 0): element["pri"] = ke_pris
        k_eles += [element]
    r_eles = []
    for r_ele in entry.iter("r_ele"):
        reb = r_ele.find("reb").text
        re_nokanji = None
        if r_ele.find("re_nokanji") is not None:
            re_nokanji = r_ele.find("re_nokanji").text
        re_restrs = []
        for re_restr in r_ele.iter("re_restr"):
            re_restrs += [re_restr.text]
        re_infs = []
        for re_inf in r_ele.iter("re_inf"):
            re_infs += [re_inf.text]
        re_pris = []
        for re_pri in r_ele.iter("re_pri"):
            re_pris += [re_pri.text]
        element = OrderedDict()
        element["reb"] = reb
        if(re_nokanji != None): element["nokanji"] = re_nokanji
        if(len(re_restrs) > 0): element["restr"] = re_restrs
        if(len(re_infs) > 0): element["inf"] = re_infs
        if(len(re_pris) > 0): element["pri"] = re_pris
        r_eles += [element]
    senses = []
    for sense in entry.iter("sense"):
        stagks = []
        for stagk in sense.iter("stagk"):
            stagks += [stagk.text]
        stagrs = []
        for stagr in sense.iter("stagr"):
            stagrs += [stagr.text]
        poss = []
        for pos in sense.iter("pos"):
            #poss += [pos.getchildren()[0].text]
            poss += [pos.text]
        xrefs = []
        for xref in sense.iter("xref"):
            xrefs += [xref.text]
        ants = []
        for ant in sense.iter("ant"):
            ants += [ant.text]
        fields = []
        for field in sense.iter("field"):
            fields += [field.text]
        miscs = []
        for misc in sense.iter("misc"):
            miscs += [misc.text]
        s_infs = []
        for s_inf in sense.iter("s_inf"):
            s_infs += [s_inf.text]
        lsources = []
        for lsource in sense.iter("lsource"):
            source = OrderedDict()
            source["text"] = lsource.text
            source["lang"] = "eng"
            if lsource.get(XML_LANG): source["lang"] = lsource.get(XML_LANG)
            source["type"] = "full"
            if lsource.get("ls_type"): source["type"] = lsource.get("ls_type")
            source["wasei"] = "n"
            if lsource.get("ls_wasei"): source["wasei"] = lsource.get("ls_wasei")
            lsources += [source]
        dials = []
        for dial in sense.iter("dial"):
            dials += [dial.text]
        glosss = []
        for gloss in sense.iter("gloss"):
            definition = OrderedDict()
            definition["text"] = gloss.text
            definition["lang"] = "eng"
            if gloss.get(XML_LANG): definition["lang"] = gloss.get(XML_LANG)
            if eng_only and definition["lang"] != "eng": continue
            if eng_only:
                glosss += [gloss.text]
            else:
                glosss += [definition]
        element = OrderedDict()
        if(len(stagks) > 0):   element["stagk"] = stagks
        if(len(stagrs) > 0):   element["stagr"] = stagrs
        if(len(poss) > 0):     element["pos"] = poss
        if(len(xrefs) > 0):    element["xref"] = xrefs
        if(len(ants) > 0):     element["ant"] = ants
        if(len(fields) > 0):   element["field"] = fields
        if(len(miscs) > 0):    element["misc"] = miscs
        if(len(s_infs) > 0):   element["inf"] = s_infs
        if(len(lsources) > 0): element["lsource"] = lsources
        if(len(dials) > 0):    element["dial"] = dials
        if(len(glosss) > 0):   element["gloss"] = glosss
        
        if(len(element) > 0): senses += [element]
        
    myentry["seq"] = seq
    if(len(k_eles) > 0): myentry["k_ele"] = k_eles
    myentry["r_ele"] = r_eles
    myentry["sense"] = senses
    entries += [myentry]

#print(entries)

#print(json.dumps(entries, ensure_ascii=False))
#sys.stdout.buffer.write(json.dumps(entries, ensure_ascii=False, separators=(',',':')).encode("utf-8"))
i = 0
under = 1
copylist = []
basename = "JMdict"
extension = ".json"
limit = 18000
for entry in entries:
    i += 1
    copylist += [entry]
    if i >= limit:
        with open(basename+str(under)+extension, "w", newline="\n", encoding="utf-8") as f:
            f.write(json.dumps(copylist, ensure_ascii=False, separators=(',',':')))
        copylist = []
        i = 0
        under += 1

with open(basename+str(under)+extension, "w", newline="\n", encoding="utf-8") as f:
    f.write(json.dumps(copylist, ensure_ascii=False, separators=(',',':')))


