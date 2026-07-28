# Part of FIQ AI. Norsk SAF-T Financial 1.30 import.
from typing import ClassVar

from odoo import Command, models


class AccountSaftImportWizard(models.TransientModel):
    _inherit = 'account.saft.import.wizard'

    # GroupingCategory (norsk SAF-T / NS 4102) -> Odoo account_type.
    # Verifisert mot 19 SAF-T-filer fra PowerOffice Go (4 selskaper, 2022-2026),
    # 1086 kontorader, 14 distinkte kategorier - alle dekket, 0 fallback.
    NO_GROUPING_CATEGORY_MAP: ClassVar[dict] = {
        'balanseverdiForAnleggsmiddel': 'asset_fixed',
        'balanseverdiForOmloepsmiddel': 'asset_current',
        'egenkapital': 'equity',
        'kortsiktigGjeld': 'liability_current',
        'langsiktigGjeld': 'liability_non_current',
        'salgsinntekt': 'income',
        'annenDriftsinntekt': 'income_other',
        'varekostnad': 'expense_direct_cost',
        'loennskostnad': 'expense',
        'annenDriftskostnad': 'expense',
        'finansinntekt': 'income_other',
        'finanskostnad': 'expense',
        'skattekostnad': 'expense',
        'resultatDisponeringForSAF-T': 'equity_unaffected',
    }

    # AnalysisType i norsk SAF-T (POG) -> analytisk plan-navn i Odoo
    NO_ANALYSIS_TYPE_MAP: ClassVar[dict] = {
        'P': 'Prosjekt',
        'A': 'Avdeling',
    }

    def _get_account_types(self):
        """Norsk SAF-T setter AccountType='GL' paa ALLE kontoer -> ubrukelig til typing.
        Typingen skjer i _prepare_account_data via GroupingCategory."""
        res = super()._get_account_types()
        res.update({'GL': 'asset_current'})
        return res

    # ------------------------------------------------------------------
    # Kompatibilitet med basemodulen (account_saft_import) paa Odoo 19
    # ------------------------------------------------------------------
    def _prepare_partner_data(self, tree):
        """Basen (account_saft_import) setter res.partner.mobile fra SAF-T MobilePhone.
        Feltet ble FJERNET fra res.partner i Odoo 19 -> ValueError 'Invalid field mobile'
        naar postene lastes. Stripper feltet defensivt hvis modellen ikke har det.
        """
        partners_to_create, partner_mapping_ids = super()._prepare_partner_data(tree)
        if 'mobile' not in self.env['res.partner']._fields:
            for vals in partners_to_create.values():
                for cmd in vals.get('child_ids') or []:
                    # Command.create -> (0, 0, {vals})
                    if isinstance(cmd, (list, tuple)) and len(cmd) == 3 and isinstance(cmd[2], dict):
                        cmd[2].pop('mobile', None)
        return partners_to_create, partner_mapping_ids

    def _prepare_opening_balance_move(self, tree, map_accounts):
        """Basen returnerer None (ikke {}) naar det ikke finnes balanseforskjell.
        _get_data gjoer da data['account.move'] = None og krasjer paa .update().
        Normaliser til tom dict.
        """
        return super()._prepare_opening_balance_move(tree, map_accounts) or {}

    def _prepare_tax_data(self, tree):
        """Basen oppretter 'SAF-T taxes'-gruppen UTEN company_id -> den havner paa
        brukerens env.company, IKKE wizardens company_id. Ved import til FLERE selskaper
        finner basens company-domene-soek den ikke, og oppretter duplikater. Da har
        `default_tax_group` flere poster og basens `.id` kaster 'Expected singleton'.

        Sikre NOEYAKTIG én company-spesifikk gruppe i domenet foer super():
          - 0 grupper  -> opprett én med riktig company_id (basen finner den, lager ingen)
          - 2+ grupper -> dedup: flytt taxes til den eldste, slett resten
        """
        Group = self.env['account.tax.group']
        domain = [*Group._check_company_domain(self.company_id), ('name', '=', 'SAF-T taxes')]
        grupper = Group.search(domain)
        if not grupper:
            Group.create({
                'name': 'SAF-T taxes',
                'company_id': self.company_id.id,
                'country_id': self.company_id.account_fiscal_country_id.id,
            })
        elif len(grupper) > 1:
            behold = grupper[0]
            resten = grupper[1:]
            self.env['account.tax'].search(
                [('tax_group_id', 'in', resten.ids)]).write({'tax_group_id': behold.id})
            resten.unlink()
        return super()._prepare_tax_data(tree)

    # ------------------------------------------------------------------
    # Kontoplan
    # ------------------------------------------------------------------
    def _prepare_account_data(self, tree):
        """Full overstyring for norsk SAF-T 1.30 (kan IKKE kalle super()).

        Generisk modul gjoer `element.find('saft:StandardAccountID').text` - direkte .text-kall.
        I norske filer er StandardAccountID TOM (0 forekomster verifisert), saa super() ville
        kastet AttributeError paa foerste konto. Derfor reimplementert her:
          1) kontokode = AccountID (fallback naar StandardAccountID mangler)
          2) kontotype = GroupingCategory (POG/NS 4102) i stedet for AccountType
        """
        nsmap = self._get_cleaned_namespace(tree)

        existing_accounts = self.env['account.account'].with_company(self.company_id).search_fetch(
            self.env['account.account']._check_company_domain(self.company_id),
            field_names=['id', 'code'],
        )
        existing_accounts_code = {account.code: account.id for account in existing_accounts}

        accounts_to_create = {}
        account_mapping_ids = {}

        for element_account in tree.findall('.//saft:Account', namespaces=nsmap):
            acc_id_node = element_account.find('saft:AccountID', namespaces=nsmap)
            if acc_id_node is None or not acc_id_node.text:
                continue
            account_id = acc_id_node.text.strip()

            std_node = element_account.find('saft:StandardAccountID', namespaces=nsmap)
            if std_node is not None and std_node.text and std_node.text.strip():
                account_code = std_node.text.strip()
            else:
                account_code = account_id

            opening_debit = element_account.find('saft:OpeningDebitBalance', namespaces=nsmap)
            opening_credit = element_account.find('saft:OpeningCreditBalance', namespaces=nsmap)
            if opening_debit is not None and opening_debit.text:
                balance = float(opening_debit.text)
            elif opening_credit is not None and opening_credit.text:
                balance = -float(opening_credit.text)
            else:
                balance = 0.0
            account_mapping_ids[account_id] = {'balance': balance}

            if account_code in existing_accounts_code:
                account_mapping_ids[account_id]['id'] = existing_accounts_code[account_code]
                continue

            grp_node = element_account.find('saft:GroupingCategory', namespaces=nsmap)
            grouping = grp_node.text.strip() if (grp_node is not None and grp_node.text) else None
            if grouping and grouping in self.NO_GROUPING_CATEGORY_MAP:
                account_type = self.NO_GROUPING_CATEGORY_MAP[grouping]
            else:
                type_node = element_account.find('saft:AccountType', namespaces=nsmap)
                type_key = type_node.text.strip() if (type_node is not None and type_node.text) else None
                account_type = self._get_account_types().get(type_key, 'asset_current')

            desc_node = element_account.find('saft:AccountDescription', namespaces=nsmap)
            name = desc_node.text.strip() if (desc_node is not None and desc_node.text) else account_code

            xml_id = self._make_xml_id('account', account_code)
            accounts_to_create[xml_id] = {
                'company_ids': [Command.link(self.company_id.id)],
                'code': account_code,
                'account_type': account_type,
                'name': name,
            }
            existing_accounts_code[account_code] = xml_id
            account_mapping_ids[account_id]['id'] = xml_id

        return accounts_to_create, account_mapping_ids

    # ------------------------------------------------------------------
    # Analytiske dimensjoner (Prosjekt / Avdeling)
    # ------------------------------------------------------------------
    def _no_saft_prepare_analytic(self, tree):
        """Leser AnalysisTypeTable og oppretter analytiske planer + kontoer.

        Norsk SAF-T (POG) legger dimensjonene i AnalysisTypeTableEntry:
          AnalysisType 'P' = Prosjekt, 'A' = Avdeling
          AnalysisID + AnalysisIDDescription = kode + navn
        Den generiske modulen leser IKKE dette. Uten dette gaar prosjekt-/avdelingskoblingen
        tapt paa hver bilagslinje.

        :returns: {(analysis_type, analysis_id): analytic_account_id}
        """
        nsmap = self._get_cleaned_namespace(tree)
        mapping = {}

        plans_by_type = {}
        for atype, plan_name in self.NO_ANALYSIS_TYPE_MAP.items():
            plan = self.env['account.analytic.plan'].search([('name', '=', plan_name)], limit=1)
            if not plan:
                plan = self.env['account.analytic.plan'].create({'name': plan_name})
            plans_by_type[atype] = plan

        for entry in tree.findall('.//saft:AnalysisTypeTableEntry', namespaces=nsmap):
            t_node = entry.find('saft:AnalysisType', namespaces=nsmap)
            id_node = entry.find('saft:AnalysisID', namespaces=nsmap)
            desc_node = entry.find('saft:AnalysisIDDescription', namespaces=nsmap)
            if t_node is None or id_node is None or not t_node.text or not id_node.text:
                continue
            atype = t_node.text.strip()
            acode = id_node.text.strip()
            if atype not in plans_by_type:
                continue
            aname = desc_node.text.strip() if (desc_node is not None and desc_node.text) else acode
            plan = plans_by_type[atype]

            analytic = self.env['account.analytic.account'].search([
                ('plan_id', '=', plan.id),
                ('code', '=', acode),
                ('company_id', 'in', [self.company_id.id, False]),
            ], limit=1)
            if not analytic:
                analytic = self.env['account.analytic.account'].create({
                    'name': aname,
                    'code': acode,
                    'plan_id': plan.id,
                    'company_id': self.company_id.id,
                })
            mapping[(atype, acode)] = analytic.id
        return mapping

    def _prepare_journal_data(self, tree, default_currency, map_accounts, map_taxes, map_currencies, map_partners):
        """Bygger analytisk kart FOER bilagene leses, saa _prepare_move_data kan bruke det.

        Kartet foeres via context, IKKE som instansattributt: Odoo-recordsets har
        __slots__ og kan ikke baere vilkaarlige attributter (ellers AttributeError).
        Basemetoden kaller self._prepare_move_data paa samme self, saa konteksten propagerer dit.
        """
        # POGs JournalID er en 15-tegns hash (alle med prefiks '8dee3'). Odoo journal.code er
        # maks 5 tegn -> avkortes til samme '8dee3' og KOLLIDERER paa tvers av aar ved fler-aars
        # import ('Journal codes must be unique per company'). Sett en kort, unik kode per aar:
        # SAF<YY>. Aaret gjoer ogsaa move-xml_id unik paa tvers av aarsfiler, siden POG gjenbruker
        # TransactionID per aar.
        nsmap = self._get_cleaned_namespace(tree)
        yn = tree.find('.//saft:PeriodStartYear', namespaces=nsmap)
        year = yn.text.strip() if (yn is not None and yn.text) else None
        if year:
            for j in tree.findall('.//saft:Journal', namespaces=nsmap):
                jid = j.find('saft:JournalID', namespaces=nsmap)
                if jid is not None and jid.text:
                    jid.text = f'SAF{year[-2:]}'

        analytic_map = self._no_saft_prepare_analytic(tree)
        wiz = self.with_context(no_saft_analytic_map=analytic_map)
        return super(AccountSaftImportWizard, wiz)._prepare_journal_data(
            tree, default_currency, map_accounts, map_taxes, map_currencies, map_partners)

    def _prepare_move_data(self, journal_tree, default_currency, saft_journal_code, journal_id,
                           map_accounts, map_taxes, map_currencies, map_partners):
        """Legger analytisk distribusjon (Prosjekt/Avdeling) paa hver bilagslinje.

        Generisk modul ignorerer <Analysis>. Vi lar den bygge bilagene, og beriker
        linjene etterpaa ved aa lese Analysis-blokkene i samme rekkefoelge.
        """
        # Norsk POG gjenbruker TransactionID baade paa tvers av OG innen samme periode
        # (verifisert: ulike bilag, samme ID). Basen bruker (journal, TransactionID) som
        # xml_id-noekkel og OVERSKRIVER kolliderende bilag -> STILLE DATATAP. Gjoer ID-en
        # unik med Period + loepenummer FOER basen leser treet. Berikelsen nedenfor leser
        # samme (modifiserte) tre, saa noeklene matcher fortsatt. Stabil for samme fil
        # (rekkefoelge-basert) -> idempotent ved gjen-import.
        nsmap = self._get_cleaned_namespace(journal_tree)
        seen = {}
        for move_node in journal_tree.findall('saft:Transaction', namespaces=nsmap):
            tid_node = move_node.find('saft:TransactionID', namespaces=nsmap)
            if tid_node is None or not tid_node.text:
                continue
            per_node = move_node.find('saft:Period', namespaces=nsmap)
            per = per_node.text if (per_node is not None and per_node.text) else '0'
            key = (tid_node.text, per)
            n = seen.get(key, 0) + 1
            seen[key] = n
            tid_node.text = f'{tid_node.text}/{per}' if n == 1 else f'{tid_node.text}/{per}.{n}'

        moves = super()._prepare_move_data(
            journal_tree, default_currency, saft_journal_code, journal_id,
            map_accounts, map_taxes, map_currencies, map_partners,
        )
        analytic_map = self.env.context.get('no_saft_analytic_map')
        if not analytic_map:
            return moves

        nsmap = self._get_cleaned_namespace(journal_tree)

        # Bygg samme noekkel som basismetoden: xml_id per Transaction
        for move_node in journal_tree.findall('saft:Transaction', namespaces=nsmap):
            name_node = move_node.find('./saft:TransactionID', namespaces=nsmap)
            if name_node is None or not name_node.text:
                continue
            xml_id = self._make_xml_id('move', f'{saft_journal_code}_{name_node.text}')
            move_vals = moves.get(xml_id)
            if not move_vals:
                continue  # allerede importert (idempotens) eller hoppet over

            line_nodes = move_node.findall('.//saft:Line', namespaces=nsmap)
            line_cmds = move_vals.get('line_ids') or []
            for idx, line_node in enumerate(line_nodes):
                if idx >= len(line_cmds):
                    break
                distribution = {}
                for an in line_node.findall('saft:Analysis', namespaces=nsmap):
                    t = an.find('saft:AnalysisType', namespaces=nsmap)
                    i = an.find('saft:AnalysisID', namespaces=nsmap)
                    if t is None or i is None or not t.text or not i.text:
                        continue
                    analytic_id = analytic_map.get((t.text.strip(), i.text.strip()))
                    if analytic_id:
                        distribution[str(analytic_id)] = 100.0
                if distribution:
                    # line_cmds[idx] = (0, 0, vals)
                    cmd = line_cmds[idx]
                    if isinstance(cmd, (list, tuple)) and len(cmd) == 3 and isinstance(cmd[2], dict):
                        cmd[2]['analytic_distribution'] = distribution
        return moves
