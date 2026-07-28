# Part of FIQ AI. PORT 6-tester for norsk SAF-T-import.
"""
Tester som OPPRETTER tilstanden de verner mot (PORT 6, brain/00_FERDIG.md).

Bakgrunn: «En test som bare LESER eksisterende data kan ikke bevise fravaer av
data-betingede krasj.» 42 gronne tester paa tynn base skjulte en TypeError.

Derfor bygger hver test sin EGEN SAF-T-fil med nettopp den datakombinasjonen
som kan felle koden — ikke en fasitfil som tilfeldigvis er snill.

Kodeveiene som testes er de to avvikene modulen finnes for:
  1. StandardAccountID TOM  -> generisk modul kaster AttributeError paa
     forste konto. Vi beviser at fallback til AccountID holder.
  2. AccountType='GL' paa alle -> ubrukelig til typing. Vi beviser at
     GroupingCategory gir riktig kontotype for alle 14 kategoriene.
Pluss analytiske dimensjoner (Prosjekt/Avdeling) som generisk modul ignorerer.
"""
import base64

from lxml import etree
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

NS = 'urn:StandardAuditFile-Taxation-Financial:NO'


def _saft(accounts_xml='', analysis_xml='', journals_xml='', suppliers_xml='', year='2099'):
    """Bygger en minimal, men GYLDIG norsk SAF-T 1.30-fil."""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<AuditFile xmlns="{NS}">
  <Header>
    <AuditFileVersion>1.30</AuditFileVersion>
    <AuditFileCountry>NO</AuditFileCountry>
    <DefaultCurrencyCode>NOK</DefaultCurrencyCode>
    <SelectionCriteria>
      <PeriodStart>1</PeriodStart><PeriodStartYear>{year}</PeriodStartYear>
      <PeriodEnd>12</PeriodEnd><PeriodEndYear>{year}</PeriodEndYear>
    </SelectionCriteria>
  </Header>
  <MasterFiles>
    <GeneralLedgerAccounts>{accounts_xml}</GeneralLedgerAccounts>
    <AnalysisTypeTable>{analysis_xml}</AnalysisTypeTable>
    <Suppliers>{suppliers_xml}</Suppliers>
  </MasterFiles>
  <GeneralLedgerEntries>{journals_xml}</GeneralLedgerEntries>
</AuditFile>"""


def _linje(account_id, debit=None, credit=None, analyse=None, record_id='1'):
    """Bilagslinje. analyse=('P','kode') gir analytisk dimensjon (Prosjekt/Avdeling)."""
    amt = (f'<DebitAmount><Amount>{debit}</Amount></DebitAmount>' if debit is not None
           else f'<CreditAmount><Amount>{credit}</Amount></CreditAmount>')
    an = (f'<Analysis><AnalysisType>{analyse[0]}</AnalysisType><AnalysisID>{analyse[1]}</AnalysisID></Analysis>'
          if analyse else '')
    return (f'<Line><RecordID>{record_id}</RecordID><AccountID>{account_id}</AccountID>'
            f'<Description>Testlinje</Description>{amt}{an}</Line>')


def _bilag(trans_id, period, linjer_xml, dato='2099-06-15'):
    return (f'<Transaction><TransactionID>{trans_id}</TransactionID><Period>{period}</Period>'
            f'<PeriodYear>2099</PeriodYear><TransactionDate>{dato}</TransactionDate>{linjer_xml}</Transaction>')


def _journal(trans_xml, journal_id='8dee3ffffffffffLANGHASH'):
    """JournalID er en 15-tegns hash, som i ekte POG-filer (kollidert paa 5-tegns kode)."""
    return (f'<Journal><JournalID>{journal_id}</JournalID><Description>Hovedbok</Description>'
            f'<Type>GL</Type>{trans_xml}</Journal>')


def _leverandor_med_mobil():
    """Leverandor med MobilePhone — feltet basen setter, men som Odoo 19 fjernet fra res.partner."""
    return ('<Supplier><SupplierID>SUP1</SupplierID><RegistrationNumber>999888777</RegistrationNumber>'
            '<Name>Testleverandor</Name>'
            '<Address><StreetName>Testveien 1</StreetName><City>Oslo</City>'
            '<PostalCode>0001</PostalCode><Country>NO</Country></Address>'
            '<Contact><ContactPerson><FirstName>Kari</FirstName><LastName>Nordmann</LastName></ContactPerson>'
            '<Telephone>22334455</Telephone><MobilePhone>99887766</MobilePhone></Contact></Supplier>')


def _konto(account_id, grouping=None, std_account_id='', desc='Test',
           opening_debit=None, opening_credit=None, account_type='GL'):
    """Norsk SAF-T-konto. std_account_id='' = TOM, som i ekte norske filer."""
    grp = f'<GroupingCategory>{grouping}</GroupingCategory>' if grouping else ''
    ob = f'<OpeningDebitBalance>{opening_debit}</OpeningDebitBalance>' if opening_debit is not None else ''
    oc = f'<OpeningCreditBalance>{opening_credit}</OpeningCreditBalance>' if opening_credit is not None else ''
    return f"""<Account>
      <AccountID>{account_id}</AccountID>
      <AccountDescription>{desc}</AccountDescription>
      <StandardAccountID>{std_account_id}</StandardAccountID>
      <AccountType>{account_type}</AccountType>
      {grp}{ob}{oc}
    </Account>"""


@tagged('post_install', '-at_install', 'fiq')
class TestNoSaftImport(AccountTestInvoicingCommon):

    @classmethod
    @AccountTestInvoicingCommon.setup_country('no')
    def setUpClass(cls):
        super().setUpClass()
        # attachment_id er required paa wizarden — create({}) feiler.
        # Innholdet er likegyldig her; testene kaller _prepare_*-metodene
        # direkte med sitt eget tre.
        #
        # 🔑 company_id MAA settes eksplisitt til testselskapet.
        # account.account.code er SELSKAPSAVHENGIG i Odoo 19 (lagres i
        # code_store som jsonb: {"<selskaps-id>": "<kode>"}), og
        # _prepare_account_data slaar opp eksisterende kontoer med
        # .with_company(self.company_id). Uten riktig selskap her leter
        # koden i feil selskap og finner ingenting.
        cls.wizard = cls.env['account.saft.import.wizard'].create({
            'attachment_name': 'test.xml',
            'attachment_id': base64.b64encode(b'<AuditFile/>'),
            'company_id': cls.env.company.id,
        })

    def _kontokode(self, konto):
        """Leser kontokoden i wizardens selskap — code er selskapsavhengig i 19."""
        return konto.with_company(self.wizard.company_id).code

    def _tree(self, xml_string):
        return etree.fromstring(xml_string.encode('utf-8'))

    # ------------------------------------------------------------------
    # KODEVEI 1: StandardAccountID er TOM (den som kastet AttributeError)
    # ------------------------------------------------------------------
    def test_tom_standard_account_id_faller_tilbake_paa_account_id(self):
        """Ekte norsk fil: StandardAccountID finnes som node, men er TOM.

        Generisk modul gjor .find(...).text direkte -> AttributeError paa
        forste konto. Dette er selve grunnen til at modulen finnes.
        """
        tree = self._tree(_saft(accounts_xml=_konto('TST3000', 'salgsinntekt')))
        to_create, mapping = self.wizard._prepare_account_data(tree)

        self.assertEqual(len(to_create), 1, 'Kontoen skal opprettes')
        vals = next(iter(to_create.values()))
        self.assertEqual(vals['code'], 'TST3000',
                         'Kontokoden skal komme fra AccountID naar StandardAccountID er tom')
        self.assertIn('TST3000', mapping)

    def test_utfylt_standard_account_id_vinner(self):
        """Er StandardAccountID FYLT UT, skal den brukes — ikke fallbacken."""
        tree = self._tree(_saft(
            accounts_xml=_konto('TST3000', 'salgsinntekt', std_account_id='TST3010')))
        to_create, _ = self.wizard._prepare_account_data(tree)
        self.assertEqual(next(iter(to_create.values()))['code'], 'TST3010')

    def test_konto_helt_uten_standard_account_id_node(self):
        """Noden mangler helt (ikke bare tom) — skal ikke krasje."""
        xml = """<Account>
          <AccountID>TST3000</AccountID>
          <AccountDescription>Salg</AccountDescription>
          <AccountType>GL</AccountType>
          <GroupingCategory>salgsinntekt</GroupingCategory>
        </Account>"""
        tree = self._tree(_saft(accounts_xml=xml))
        to_create, _ = self.wizard._prepare_account_data(tree)
        self.assertEqual(next(iter(to_create.values()))['code'], 'TST3000')

    def test_konto_uten_account_id_hoppes_over_uten_krasj(self):
        """Rad uten AccountID i det hele tatt — skal hoppes over, ikke felle importen."""
        xml = '<Account><AccountDescription>Soppel</AccountDescription></Account>'
        tree = self._tree(_saft(accounts_xml=xml + _konto('TST3000', 'salgsinntekt')))
        to_create, _ = self.wizard._prepare_account_data(tree)
        self.assertEqual(len(to_create), 1, 'Kun den gyldige kontoen skal opprettes')

    # ------------------------------------------------------------------
    # KODEVEI 2: GroupingCategory -> kontotype (AccountType='GL' er ubrukelig)
    # ------------------------------------------------------------------
    def test_alle_fjorten_grupperingskategorier_gir_riktig_type(self):
        """Alle 14 kategoriene R01.04 fant i 19 filer / 1086 kontorader.

        Feiler denne, er kartet ufullstendig og kontoer faar feil type i regnskapet.
        """
        kart = self.wizard.NO_GROUPING_CATEGORY_MAP
        self.assertEqual(len(kart), 14, 'Kartet skal dekke 14 kategorier')

        konti = ''.join(
            _konto(f'TST{4000 + i:04d}', grouping)
            for i, grouping in enumerate(kart)
        )
        tree = self._tree(_saft(accounts_xml=konti))
        to_create, _ = self.wizard._prepare_account_data(tree)

        self.assertEqual(len(to_create), 14)
        faktiske = {v['code']: v['account_type'] for v in to_create.values()}
        for i, (grouping, ventet) in enumerate(kart.items()):
            self.assertEqual(faktiske[f'TST{4000 + i:04d}'], ventet,
                             f'{grouping} skal gi {ventet}')

    def test_ukjent_grupperingskategori_faller_tilbake_uten_krasj(self):
        """Ny/ukjent kategori fra POG skal ikke felle importen."""
        tree = self._tree(_saft(
            accounts_xml=_konto('TST9999', 'heltNyKategoriIngenHarSett')))
        to_create, _ = self.wizard._prepare_account_data(tree)
        self.assertEqual(len(to_create), 1)
        self.assertEqual(next(iter(to_create.values()))['account_type'], 'asset_current')

    def test_gl_account_type_er_registrert(self):
        """AccountType='GL' maa finnes i kartet, ellers krasjer fallbacken."""
        self.assertEqual(self.wizard._get_account_types().get('GL'), 'asset_current')

    def test_konto_uten_grouping_bruker_account_type(self):
        """Mangler GroupingCategory -> fall tilbake paa AccountType."""
        tree = self._tree(_saft(accounts_xml=_konto('TST1500', grouping=None)))
        to_create, _ = self.wizard._prepare_account_data(tree)
        self.assertEqual(next(iter(to_create.values()))['account_type'], 'asset_current')

    # ------------------------------------------------------------------
    # SALDOER — inngaaende balanse, begge fortegn
    # ------------------------------------------------------------------
    def test_inngaaende_saldo_debet_og_kredit(self):
        """Kredit skal bli NEGATIV. Feil fortegn her gir feil i hele regnskapet."""
        tree = self._tree(_saft(accounts_xml=(
            _konto('TST1500', 'balanseverdiForOmloepsmiddel', opening_debit='1000.50')
            + _konto('TST2400', 'kortsiktigGjeld', opening_credit='750.25')
            + _konto('TST3000', 'salgsinntekt')
        )))
        _, mapping = self.wizard._prepare_account_data(tree)
        self.assertAlmostEqual(mapping['TST1500']['balance'], 1000.50)
        self.assertAlmostEqual(mapping['TST2400']['balance'], -750.25)
        self.assertAlmostEqual(mapping['TST3000']['balance'], 0.0,
                               msg='Uten saldo skal balansen vaere 0, ikke None')

    # ------------------------------------------------------------------
    # EKSISTERENDE KONTOER — importen skal ikke lage dubletter
    # ------------------------------------------------------------------
    def test_eksisterende_konto_gjenbrukes_ikke_dupliseres(self):
        """Kjores importen to ganger, skal ikke kontoene opprettes paa nytt."""
        # .with_company() er noedvendig: code er selskapsavhengig i Odoo 19,
        # saa kontoen maa opprettes i SAMME selskap som wizarden leser i.
        eksisterende = self.env['account.account'].with_company(
            self.wizard.company_id).create({
            'code': 'TST3000',
            'name': 'Salgsinntekt',
            'account_type': 'income',
            'company_ids': [(4, self.wizard.company_id.id)],
        })
        tree = self._tree(_saft(accounts_xml=_konto('TST3000', 'salgsinntekt')))
        to_create, mapping = self.wizard._prepare_account_data(tree)

        self.assertEqual(len(to_create), 0, 'Eksisterende konto skal ikke opprettes paa nytt')
        self.assertEqual(mapping['TST3000']['id'], eksisterende.id)

    def test_blandet_eksisterende_og_nye(self):
        """Realistisk import: noen kontoer finnes, andre ikke."""
        self.env['account.account'].with_company(self.wizard.company_id).create({
            'code': 'TST3000', 'name': 'Salg', 'account_type': 'income',
            'company_ids': [(4, self.wizard.company_id.id)],
        })
        tree = self._tree(_saft(accounts_xml=(
            _konto('TST3000', 'salgsinntekt')
            + _konto('TST4000', 'varekostnad')
            + _konto('TST5000', 'loennskostnad')
        )))
        to_create, mapping = self.wizard._prepare_account_data(tree)
        self.assertEqual(len(to_create), 2, 'Kun de to nye skal opprettes')
        self.assertEqual(len(mapping), 3, 'Alle tre skal vaere i kartet')

    # ------------------------------------------------------------------
    # ANALYTISKE DIMENSJONER — Prosjekt/Avdeling (generisk modul ignorerer)
    # ------------------------------------------------------------------
    def test_analysetabell_oppretter_planer_og_kontoer(self):
        analysis = """
          <AnalysisTypeTableEntry>
            <AnalysisType>P</AnalysisType>
            <AnalysisID>26_045</AnalysisID>
            <AnalysisIDDescription>ERP-oppdatering</AnalysisIDDescription>
          </AnalysisTypeTableEntry>
          <AnalysisTypeTableEntry>
            <AnalysisType>A</AnalysisType>
            <AnalysisID>10</AnalysisID>
            <AnalysisIDDescription>Administrasjon</AnalysisIDDescription>
          </AnalysisTypeTableEntry>"""
        tree = self._tree(_saft(analysis_xml=analysis))
        kart = self.wizard._no_saft_prepare_analytic(tree)

        self.assertIn(('P', '26_045'), kart)
        self.assertIn(('A', '10'), kart)
        self.assertTrue(self.env['account.analytic.plan'].search([('name', '=', 'Prosjekt')]))
        self.assertTrue(self.env['account.analytic.plan'].search([('name', '=', 'Avdeling')]))

    def test_ukjent_analysetype_hoppes_over(self):
        """Kun P og A er kjent. En tredje type skal ignoreres, ikke krasje."""
        analysis = """
          <AnalysisTypeTableEntry>
            <AnalysisType>X</AnalysisType>
            <AnalysisID>99</AnalysisID>
            <AnalysisIDDescription>Ukjent</AnalysisIDDescription>
          </AnalysisTypeTableEntry>"""
        tree = self._tree(_saft(analysis_xml=analysis))
        kart = self.wizard._no_saft_prepare_analytic(tree)
        self.assertEqual(kart, {})

    def test_analysetabell_er_idempotent(self):
        """To kjoringer skal ikke lage dubletter av analytiske kontoer."""
        analysis = """
          <AnalysisTypeTableEntry>
            <AnalysisType>P</AnalysisType>
            <AnalysisID>26_045</AnalysisID>
            <AnalysisIDDescription>ERP</AnalysisIDDescription>
          </AnalysisTypeTableEntry>"""
        tree = self._tree(_saft(analysis_xml=analysis))
        forste = self.wizard._no_saft_prepare_analytic(tree)
        andre = self.wizard._no_saft_prepare_analytic(tree)
        self.assertEqual(forste, andre, 'Andre kjoring skal gjenbruke samme konto')

    def test_tom_analysetabell_gir_tomt_kart(self):
        """Filer uten dimensjoner skal ikke felle importen."""
        tree = self._tree(_saft())
        self.assertEqual(self.wizard._no_saft_prepare_analytic(tree), {})

    # ------------------------------------------------------------------
    # MENGDE — nærmer seg ekte importvolum
    # ------------------------------------------------------------------
    def test_stor_kontoplan(self):
        """~800 kontoer, som i selskap 2. Beviser at ingenting er kvadratisk
        eller feiler over en viss mengde."""
        kategorier = list(self.wizard.NO_GROUPING_CATEGORY_MAP)
        konti = ''.join(
            _konto(f'TST{10000 + i:05d}', kategorier[i % len(kategorier)],
                   opening_debit=str(i * 1.5))
            for i in range(800)
        )
        tree = self._tree(_saft(accounts_xml=konti))
        to_create, mapping = self.wizard._prepare_account_data(tree)
        self.assertEqual(len(to_create), 800)
        self.assertEqual(len(mapping), 800)

    def test_xml_id_taaler_mellomrom_i_kode(self):
        """_make_xml_id kaster ValueError paa understrek i PREFIX, og
        mellomrom i noekkel byttes til understrek. Kontokoder med mellomrom
        finnes i ekte filer."""
        xml_id = self.wizard._make_xml_id('account', '1500 20')
        self.assertNotIn(' ', xml_id)

    # ------------------------------------------------------------------
    # FULL IMPORT — action_import fra ende til ende.
    # 🔴 De 17 testene over kaller _prepare_*-metodene ISOLERT. Det er nettopp
    # «proevekjoert logikk != faktisk import» (00_FERDIG): fem feil oppstod KUN
    # i den fulle importflyten og ble derfor aldri fanget. Denne testen kjorer
    # action_import og verner mot alle fem (R01.06, verifisert 28.07 mot 19 ekte
    # filer, 0 tap).
    # ------------------------------------------------------------------
    def test_full_import_verner_mot_alle_fem_feilene(self):
        """Full action_import med data som treffer hver feil:
        (1) instansattributt-state (recordset __slots__ -> AttributeError),
        (2) opening balance = None -> _get_data krasjer,
        (3) mobiltelefon-felt fjernet i Odoo 19 -> Invalid field,
        (4) TransactionID gjenbrukt -> bilag overskrevet (stille datatap),
        (5) journal-kode > 5 tegn -> 'Journal codes must be unique'.
        """
        accounts = (_konto('TST1500', 'balanseverdiForOmloepsmiddel')
                    + _konto('TST3000', 'salgsinntekt'))
        analysis = ('<AnalysisTypeTableEntry><AnalysisType>P</AnalysisType>'
                    '<AnalysisID>TSTPRJ</AnalysisID>'
                    '<AnalysisIDDescription>Prosjekt</AnalysisIDDescription></AnalysisTypeTableEntry>')
        # to bilag med SAMME TransactionID (ulik Period) — POG gjenbruker ID
        b1 = _bilag('1', '3', _linje('TST1500', debit='100.00', analyse=('P', 'TSTPRJ'))
                    + _linje('TST3000', credit='100.00', record_id='2'))
        b2 = _bilag('1', '4', _linje('TST1500', debit='250.00')
                    + _linje('TST3000', credit='250.00', record_id='2'))
        xml = _saft(accounts_xml=accounts, analysis_xml=analysis,
                    suppliers_xml=_leverandor_med_mobil(), journals_xml=_journal(b1 + b2))

        self.wizard.attachment_id = base64.b64encode(xml.encode('utf-8'))
        self.wizard.import_opening_balance = True  # (2) skal ikke krasje
        self.wizard.action_import()

        company = self.wizard.company_id
        moves = self.env['account.move'].search([('company_id', '=', company.id)])
        # (4) begge kolliderende bilag bevart — ikke overskrevet
        self.assertEqual(
            len(moves), 2,
            'Begge bilag med samme TransactionID skal bevares — ellers stille datatap')
        # (5) journal-kode kort nok for Odoos 5-tegns felt
        journal = moves.journal_id
        self.assertEqual(len(journal), 1, 'Alle bilag skal havne i samme SAF-T-journal')
        self.assertLessEqual(len(journal.code), 5, 'Journal-kode maa passe i journal.code (size 5)')
        # (3) analytisk distribusjon lagt paa linjen
        self.assertTrue(
            moves.line_ids.filtered('analytic_distribution'),
            'Prosjekt/Avdeling skal legges som analytisk distribusjon')
        # regnskapsintegritet
        self.assertEqual(
            sum(moves.line_ids.mapped('debit')), sum(moves.line_ids.mapped('credit')),
            'Bilagene skal balansere')
        # (3-mobil) leverandoren importert uten krasj (mobile fjernet i Odoo 19)
        self.assertTrue(
            self.env['res.partner'].search([('name', '=', 'Testleverandor')]),
            'Leverandor med MobilePhone skal importeres uten at mobile-feltet feller importen')
