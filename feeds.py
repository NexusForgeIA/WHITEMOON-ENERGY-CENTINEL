"""Utilidades de lectura de RSS (Google Noticias) y filtros de «solo España» y «seguimiento»."""
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

FOREIGN = re.compile(r"\b(m[eé]xico|mexican|tamaulipas|reynosa|matamoros|cdmx|monterrey|jalisco|veracruz|oaxaca|chihuahua|sonora|yucat[aá]n|"
                     r"argentin|buenos aires|chile|santiago de chile|per[uú]\b|lima\b|colombia|bogot[aá]|medell[ií]n|venezuela|caracas|ecuador|quito|bolivia|paraguay|uruguay|"
                     r"cuba|habana|guatemala|honduras|nicaragua|costa rica|panam[aá]|puerto rico|rep[uú]blica dominicana|brasil|portugal|lisboa|oporto|francia|par[ií]s|italia|roma\b|"
                     r"alemania|berl[ií]n|reino unido|londres|india|china|jap[oó]n|ee\.? ?uu|estados unidos|nueva york|texas|california|rusia|ucrania|israel|egipto|marruecos|"
                     r"pakist[aá]n|banglad|ir[aá]n|irak|turqu[ií]a|suiza|b[eé]lgica|pa[ií]ses bajos|holanda|polonia|grecia|austria|suecia|noruega|dinamarca|sud[aá]frica|nigeria|kenia|filipinas|indonesia|tailandia|vietnam|corea|australia|canad[aá]|nyc|metro de (m[eé]xico|santiago de chile|lima|bogot[aá]|buenos aires|caracas))\b", re.I)

FOREIGN_SRC = re.compile(r"vox populi|infobae|el universal|milenio|excelsior|excélsior|la jornada|el financiero|televisa|tv azteca|el comercio|clar[ií]n|la naci[oó]n|el tiempo|semana|el espectador|"
                         r"el mercurio|la tercera|biobio|bbc|cnn|reuters|france 24|dw\b|rfi|sputnik|rt en espa|telesur|prensa latina|hispantv|univision|telemundo|"
                         r"el diario ny|la opini[oó]n de los angeles|publimetro|debate|el sol de|el informador|n\+|imagen|uno tv|aristegui|proceso|animal pol[ií]tico|"
                         r"diario de yucat[aá]n|el heraldo de (m[eé]xico|honduras)|el pa[ií]s am[eé]rica|ol[eé] brasil|\bg1\b|globo|publico\.pt|expresso|observador|sic not[ií]cias|\bcm\b|jornal", re.I)

FOREIGN_TLD = re.compile(r"\.(mx|ar|cl|pe|co|ve|ec|uy|bo|py|cr|gt|hn|ni|pa|do|cu|br|pt|fr|it|de|uk|us|ru|in|cn|jp)(/|$)", re.I)

FOLLOWUP = re.compile(r"superviviente|hospitalizad|investig|juicio|v[ií]ctimas|homenaje|funeral|duelo|balance|causas?|declara|reclama|critica|acusa|"
                      r"reanud|trabajos|piden|mantienen|maquinistas|sindicat|retrasos?|circulaci[oó]n|restablec|vuelven|dimisi|ministro|oposici|pol[ií]tic|indemniz|recuerd|testimon|muere|falleci|identific|ingresad|heridos? siguen|crisis", re.I)


def ln(t):
    return t.rsplit("}", 1)[-1]


def txt(el, *names):
    for c in el:
        if ln(c.tag) in names:
            if ln(c.tag) == "link" and not (c.text or "").strip() and c.get("href"):
                return c.get("href").strip()
            return (c.text or "").strip()
    return ""


def when(s):
    try:
        return parsedate_to_datetime(s).timestamp()
    except Exception:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None
