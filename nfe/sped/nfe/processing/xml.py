# -*- encoding: utf-8 -*-
###############################################################################
#                                                                             #
# Copyright (C) 2013  Danimar Ribeiro 22/08/2013                              #
# Copyright (C) 2013  Renato Lima - Akretion                                  #
#                                                                             #
#This program is free software: you can redistribute it and/or modify         #
#it under the terms of the GNU Affero General Public License as published by  #
#the Free Software Foundation, either version 3 of the License, or            #
#(at your option) any later version.                                          #
#                                                                             #
#This program is distributed in the hope that it will be useful,              #
#but WITHOUT ANY WARRANTY; without even the implied warranty of               #
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                #
#GNU Affero General Public License for more details.                          #
#                                                                             #
#You should have received a copy of the GNU Affero General Public License     #
#along with this program.  If not, see <http://www.gnu.org/licenses/>.        #
###############################################################################


import os
import time
import base64
import re
import string
from datetime import datetime
from os.path import expanduser

from openerp import pooler
from openerp.osv import orm
from openerp.tools.translate import _

from pysped.nfe import ProcessadorNFe
from pysped.nfe import webservices_flags

def monta_caminho_nfe(ambiente, chave_nfe):
    p = ProcessadorNFe()
    return p.monta_caminho_nfe(ambiente,chave_nfe)

def __configure(company):
    p = ProcessadorNFe()
    p.ambiente = int(company.nfe_environment)
    p.versao = '2.00' if (company.nfe_version == '200') else '1.10'
    p.estado = company.partner_id.l10n_br_city_id.state_id.code
    p.certificado.stream_certificado = base64.decodestring(company.nfe_a1_file)
    p.certificado.senha = company.nfe_a1_password
    p.salva_arquivos      = True
    p.contingencia_SCAN   = False
    p.caminho = company.nfe_export_folder or os.path.join(expanduser("~"), company.name)
    return p

def sign():
    pass

def cancel(company, invoice, justificative):
    p = __configure(company)
    
    processo = p.cancelar_nota_evento(
        chave_nfe = invoice.nfe_access_key,
        numero_protocolo=invoice.nfe_status,
        justificativa=justificative
    )
    return processo
    
def send(company, nfe):
    p = __configure(company)

    return p.processar_notas(nfe)
       
def invalidate(company, invalidate_number):
    p = __configure(company)     
            
    cnpj_partner = re.sub('[^0-9]','', company.partner_id.cnpj_cpf)
    serie = invalidate_number.document_serie_id.code

    processo = p.inutilizar_nota(
        cnpj=cnpj_partner,
        serie=serie,
        numero_inicial=invalidate_number.number_start,
        numero_final=invalidate_number.number_end,
        justificativa=invalidate_number.justificative)
               
    return processo

