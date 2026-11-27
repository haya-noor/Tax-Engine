// The app's settings page in the Stripe Dashboard: which states to collect sales tax in.
// It reads and saves the setting on the Tax Engine server (backend/settings_api.py).
// Every request is signed with fetchStripeSignature(), so the server knows it really
// comes from this Stripe account.

import {useEffect, useState} from 'react';
import {Banner, Box, Checkbox, SettingsView} from '@stripe/ui-extension-sdk/ui';
import type {ExtensionContextValue} from '@stripe/ui-extension-sdk/context';
import {fetchStripeSignature} from '@stripe/ui-extension-sdk/utils';

const BACKEND = 'https://tax-engine-titu.vercel.app/settings';

const STATE_NAMES: Record<string, string> = {
  WA: 'Washington',
};

type Settings = {collect_in: string[]; supported_states: string[]};

async function post(path: string, body: object, signature: string): Promise<Settings> {
  const response = await fetch(`${BACKEND}/${path}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'Stripe-Signature': signature},
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

const AppSettings = ({userContext}: ExtensionContextValue) => {
  const [supported, setSupported] = useState<string[]>([]);
  const [collectIn, setCollectIn] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [status, setStatus] = useState('');
  const [problem, setProblem] = useState('');

  const ids = {user_id: userContext?.id, account_id: userContext?.account.id};

  useEffect(() => {
    (async () => {
      try {
        // The server checks the signature of {user_id, account_id}.
        const settings = await post('get', ids, await fetchStripeSignature());
        setSupported(settings.supported_states);
        setCollectIn(settings.collect_in);
        setLoaded(true);
      } catch (e) {
        setProblem(`Could not load the settings: ${(e as Error).message}`);
      }
    })();
  }, []);

  const toggle = (state: string, on: boolean) =>
    setCollectIn((current) => (on ? [...current, state] : current.filter((s) => s !== state)));

  const save = async () => {
    setStatus('Saving...');
    try {
      // Signed payload is {collect_in, user_id, account_id}, in that order.
      const payload = {collect_in: collectIn};
      const settings = await post('save', {...payload, ...ids}, await fetchStripeSignature(payload));
      setCollectIn(settings.collect_in);
      setStatus('Saved');
    } catch (e) {
      setStatus(`Not saved: ${(e as Error).message}`);
    }
  };

  return (
    <SettingsView onSave={save} statusMessage={status}>
      <Box css={{stack: 'y', gap: 'medium'}}>
        <Box>
          Tax Engine adds sales tax to your draft invoices automatically, using each customer's
          address and each product's tax category. Choose the states where you are registered to
          collect sales tax. Invoices for other states get no tax.
        </Box>
        {problem && <Banner type="critical" title="Something went wrong" description={problem} />}
        {loaded &&
          supported.map((state) => (
            <Checkbox
              key={state}
              name={state}
              label={`Collect sales tax in ${STATE_NAMES[state] || state}`}
              checked={collectIn.includes(state)}
              onChange={(e) => toggle(state, e.target.checked)}
            />
          ))}
        <Box css={{font: 'caption', color: 'secondary'}}>
          More states are coming. Tax rates come from each state's Department of Revenue.
        </Box>
      </Box>
    </SettingsView>
  );
};

export default AppSettings;
