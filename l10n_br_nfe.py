# -*- encoding: utf-8 -*-
###############################################################################
#                                                                             #
# Copyright (C) 2013  Danimar Ribeiro 26/06/2013                              #
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

from openerp.osv import osv, fields, orm
import pysped.nfe, base64, re, datetime, netsvc
from openerp.tools.translate import _
from send_nfe import SendNFe

class l10n_br_nfe_send_sefaz(osv.Model):
    """ Classe para salvar o retorno dos metodos de envio de cancelamento, inutilização e recepção de nota """
    _name = 'l10n_br_nfe.send_sefaz'
    _description = 'Envia os dados para o SEFAZ NFe'
    _columns = {                
        'name': fields.char('Nome', size=255),
        'file': fields.binary('Xml processado', readonly=True),        
        'state': fields.selection(
            [('init', 'init'), ('done', 'done')], 'state', readonly=True),
        'start_date': fields.datetime('Inicio'),
        'end_date': fields.datetime('Fim'),
        'nfe_environment': fields.selection(
            [('1', u'Produção'), ('2', u'Homologação')], 'Ambiente'),        
        'nfe_export_result': fields.one2many(
            'l10n_br_nfe.send_sefaz_result', 'send_sefaz_id',
            'NFe Export Result'),        
    }
    _defaults = {
        'state': 'init',        
        'nfe_environment': '2',        
    }
    

class l10n_br_nfe_send_sefaz_result(osv.Model):
    _name = 'l10n_br_nfe.send_sefaz_result'
    _columns = {
        'send_sefaz_id': fields.many2one(
            'l10n_br_nfe.send_sefaz', 'Envio SEFAZ',
            ondelete='cascade', select=True),
        'xml_type': fields.char('Tipo', size=255),
        'name':fields.char('Nome envio', size=255),                
        'file': fields.binary('Xml envio', readonly=True),
        'name_result':fields.char('Nome retorno', size=255),        
        'file_result': fields.binary('Xml retorno', readonly=True),        
        'status': fields.selection(
            [('success', 'Sucesso'), ('error', 'Erro')], 'Status'),
        'status_code':fields.char('Código',size=5),
        'message': fields.char('Mensagem', size=255),
    }
    
class res_company(osv.Model):
    _inherit = 'res.company'
    _columns = {
        'save_xml_folder': fields.boolean('Salvar Xml na Pasta?'),
    }

class account_invoice(osv.Model):
    _inherit = 'account.invoice'
    _columns = {                               
        'send_nfe_invoice_id': fields.many2one('l10n_br_nfe.send_sefaz', 'Envio NFe'),
        'cancel_nfe_invoice_id': fields.many2one('l10n_br_nfe.send_sefaz', 'Cancelamento NFe'),
    }
    
    def action_invoice_send_nfe(self, cr, uid, ids, context=None):
        record = self.browse(cr, uid, ids[0])
        company_pool = self.pool.get('res.company')        
        company = company_pool.browse(cr, uid, record.company_id.id)
        
        validate_nfe_configuration(company)
        
        nfe_send_pool = self.pool.get('l10n_br_nfe.send_sefaz')
        nfe_send_id = nfe_send_pool.create(cr, uid, { 'name': 'Envio NFe', 'start_date': datetime.datetime.now()}, context)
        self.write(cr, uid, ids, {'send_nfe_invoice_id': nfe_send_id})
        
        erros = False   
        chave_nfe = ''
        status_sefaz = ''                     
        try:
            envio = SendNFe()
            resultados =  envio.send_nfe(cr, uid, ids, '2', context)
        
            nfe_send_pool.write(cr, uid, nfe_send_id,{ 'end_date': datetime.datetime.now(),'state':'done' }, context)
            result_pool =  self.pool.get('l10n_br_nfe.send_sefaz_result')
            for result in resultados:
                if result['status'] != 'success':
                    erros = True
                if result['xml_type'] == 'Recibo NF-e':
                    status_sefaz = result['status_code'] + ' - ' + result['message']
                    chave_nfe = result["nfe_key"] or ''
                                        
                result_pool.create(cr, uid, {'send_sefaz_id': nfe_send_id , 'xml_type': result['xml_type'], 
                            'name':result['name'], 'file':base64.b64encode(result['xml_sent'].encode('utf8')), 
                            'name_result':result['name_result'], 'file_result':base64.b64encode(result['xml_result'].encode('utf8')),
                            'status':result['status'], 'status_code':result['status_code'], 
                            'message':result['message']}, context)
        except Exception as e:
            status_sefaz = e.message
            erros = True
        
        data_envio = datetime.datetime.now()  
        if erros:            
            chave_nfe = ''   
            self.write(cr, uid, ids, {'state':'sefaz_exception'}, context)                                 
        else:            
            self.write(cr, uid, ids, {'state':'open'}, context)          
        
        self.write(cr, uid, ids, { 'nfe_access_key': chave_nfe, 'nfe_status':status_sefaz, 'nfe_date':data_envio }, context)        
        
    def action_cancel(self, cr, uid, ids, context=None):
        self.cancel_invoice_online(cr, uid, ids, context)
        return  super(account_invoice,self).action_cancel(cr, uid, ids, context)
        
    def cancel_invoice_online(self, cr, uid, ids,context=None):        
        record = self.browse(cr, uid, ids[0])
        if record.document_serie_id:
            if record.document_serie_id.fiscal_document_id:
                if not record.document_serie_id.fiscal_document_id.electronic:
                    return
                
        if record.state in ('open','paid'): 
            company_pool = self.pool.get('res.company')        
            company = company_pool.browse(cr, uid, record.company_id.id)
            
            validate_nfe_configuration(company)
            validate_invoice_cancel(record)            
                
            p = pysped.nfe.ProcessadorNFe()
            p.versao = company.nfe_version
            p.estado = company.partner_id.l10n_br_city_id.state_id.code
            
            file_content_decoded = base64.decodestring(company.nfe_a1_file)
            filename = company.nfe_export_folder + 'certificate.pfx'
            fichier = open(filename,'w+')
            fichier.write(file_content_decoded)
            fichier.close()
                       
            p.certificado.arquivo = filename
            p.certificado.senha = company.nfe_a1_password
        
            p.salva_arquivos = company.save_xml_folder
            p.contingencia_SCAN = False
            p.caminho = company.nfe_export_folder
            
            processo = p.cancelar_nota_evento(
                chave_nfe = record.nfe_access_key,
                numero_protocolo=record.nfe_status,
                justificativa='Somente um teste de cancelamento' #TODO Colocar a justificativa de cancelamento num wizard de cancelamento.
            )

            #TODO Salvar esses dados ainda em algum lugar.
            print processo        
            print processo.envio.xml
            print processo.envio.original
            print processo.resposta.xml
            print processo.resposta.original
            print processo.resposta.reason
            print processo.resposta.dic_retEvento
            print processo.resposta.dic_procEvento
        
class l10n_br_account_invoice_invalid_number(osv.Model):
    _inherit = 'l10n_br_account.invoice.invalid.number'    
    _columns = {
        'invalidate_number_nfe_invoice_id': fields.many2one('l10n_br_nfe.send_sefaz', 'Inutilização numeração NFe'),            
        'state': fields.selection(
            [('draft', 'Rascunho'), ('not_authorized', 'Não autorizado'),('done', u'Autorizado Sefaz')], 'Status', required=True),        
        'status':fields.char('Status', size=10),
        'message':fields.char('Mensagem', size=200),
    }
    
    def action_draft_done(self, cr, uid, ids, *args):
        try:
            processo = self.send_request_to_sefaz(cr, uid, ids , args)
            
            if processo.resposta.infInut.cStat.valor == '102':
                self.write(cr, uid, ids, {'state': 'done', 'status':'102', 'message':processo.resposta.infInut.xMotivo.valor})
            else:
                self.write(cr, uid, ids, {'state':'not_authorized', 'status':processo.resposta.infInut.cStat.valor,
                        'message':processo.resposta.infInut.xMotivo.valor})
                
        except orm.except_orm, ex:
            raise ex          
        except Exception,e:
            raise orm.except_orm(_('Error !'), e.message)       
        return True
    
        
    def send_request_to_sefaz(self, cr, uid, ids, *args):    
        record = self.browse(cr, uid, ids[0])
        company_pool = self.pool.get('res.company')        
        company = company_pool.browse(cr, uid, record.company_id.id)
        
        validate_nfe_configuration(company)
        validate_nfe_invalidate_number(company, record)
        
        p = pysped.nfe.ProcessadorNFe()
        p.versao = '2.00' if (company.nfe_version == '200') else '1.10'
        p.estado = company.partner_id.l10n_br_city_id.state_id.code
        
        file_content_decoded = base64.decodestring(company.nfe_a1_file)
        filename = company.nfe_export_folder + 'certificate.pfx'
        fichier = open(filename,'w+')
        fichier.write(file_content_decoded)
        fichier.close()
                   
        p.certificado.arquivo = filename
        p.certificado.senha = company.nfe_a1_password
    
        p.salva_arquivos = company.save_xml_folder
        p.contingencia_SCAN = False    
        p.caminho = company.nfe_export_folder       
                
        cnpj_partner = re.sub('[^0-9]','', company.partner_id.cnpj_cpf)
        serie = record.document_serie_id.code

        processo = p.inutilizar_nota(
            cnpj=cnpj_partner,
            serie=serie,
            numero_inicial=record.number_start,
            numero_final=record.number_end,
            justificativa=record.justificative)
                   
        return processo

def validate_nfe_invalidate_number(company, record):
    error = u'As seguintes configurações estão faltando:\n'    
    if not company.partner_id or not company.partner_id.l10n_br_city_id \
        or not company.partner_id.l10n_br_city_id.state_id  or not company.partner_id.l10n_br_city_id.state_id.code:        
        error += u'Código do estado no endereço da empresa\n'
    if not company.nfe_version:
        error += u'Versão da NFe na configuração da empresa\n'
    if not company.partner_id.cnpj_cpf:
        error += u'CNPJ na configuração da empresa\n'
    if not record.document_serie_id.code:
        error += u'Série no registro de inutilização\n'
    if not record.number_start:
        error += u'Número de inicio no registro de inutilização\n'
    if not record.number_end:
        error += u'Número final no registro de inutilização\n'
    if error != u'As seguintes configurações estão faltando:\n':
        raise orm.except_orm(_('Validação !'), _(error)) 
    
def validate_invoice_cancel(invoice):
    error = u'Verifique os problemas com o cancelamento:\n'
    if not invoice.nfe_access_key:
        error += u'Nota Fiscal - Chave de acesso NF-e\n'
    if not invoice.nfe_status:
        error += u'Empresa - Protocolo de autorização na Sefaz\n'
    if error != u'Verifique os problemas com o cancelamento:\n':
        raise orm.except_orm(_('Validação !'), _(error))

def validate_nfe_configuration(company):
    error = u'As seguintes configurações estão faltando:\n'
    if not company.nfe_version:
        error += u'Empresa - Versão NF-e\n'
    if not company.nfe_a1_file:
        error += u'Empresa - Arquivo NF-e A1\n'
    if not company.nfe_a1_password:
        error += u'Empresa - Senha NF-e A1\n'
    if not company.nfe_export_folder and company.save_xml_folder:
        error += u'Empresa - Pasta de exportação\n'
    if error != u'As seguintes configurações estão faltando:\n':
        raise orm.except_orm(_('Validação !'), _(error))
