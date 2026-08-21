"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthProvider";
import { demoAccounts as fetchDemoAccounts } from "@/lib/api/resources/auth";
import type { DemoAccount } from "@/lib/api/types";
import { ROLE_LABELS } from "@/lib/labels";
import { ApiError, friendlyErrorMessage } from "@/lib/api/errors";
import { Button } from "@/components/ui/Button";
import { Field, inputClassName } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [accounts, setAccounts] = useState<DemoAccount[] | null>(null);
  const [accountsError, setAccountsError] = useState(false);
  const [retry, setRetry] = useState(0);

  // Une seule tentative condamnait l'écran : au réveil de l'hébergement, la toute
  // première requête peut échouer le temps que la base réponde, et le visiteur n'avait
  // plus que la saisie manuelle d'identifiants qu'il ne connaît pas. Trois essais espacés
  // couvrent un démarrage à froid sans jamais faire attendre quand tout va bien.
  useEffect(() => {
    let cancelled = false;

    async function load(attempt = 0): Promise<void> {
      try {
        const fetched = await fetchDemoAccounts();
        if (!cancelled) setAccounts(fetched);
      } catch {
        if (cancelled) return;
        if (attempt < 2) {
          setTimeout(() => void load(attempt + 1), 1200 * (attempt + 1));
          return;
        }
        setAccountsError(true);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [retry]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      router.replace("/shootings");
    } catch (err) {
      if (err instanceof ApiError && err.isNotImplemented) {
        setError("La connexion n'est pas encore branchée côté serveur (route 501).");
      } else {
        setError(friendlyErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  function fillDemo(account: DemoAccount) {
    setEmail(account.email);
    setPassword(account.password);
    setError(null);
  }

  return (
    <div className="rounded-2xl border border-ink-800 bg-ink-900 p-8 shadow-2xl">
      <div className="mb-6 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent-500">Apex</p>
        <h1 className="mt-1 text-lg font-semibold text-white">Studio photo motorsport</h1>
        <p className="mt-1 text-sm text-ink-300">Connexion à l&apos;espace interne</p>
      </div>

      {accounts && accounts.length > 0 ? (
        <div className="mb-6 flex flex-col gap-2">
          <p className="text-xs font-medium text-ink-400">Comptes de démonstration</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            {accounts.map((account) => (
              <button
                key={account.email}
                type="button"
                onClick={() => fillDemo(account)}
                className="flex-1 rounded-lg border border-ink-700 bg-ink-800 px-3 py-2.5 text-left text-sm text-white transition-colors hover:border-accent-500 hover:bg-ink-700 focus-visible:outline-2 focus-visible:outline-accent-500 focus-visible:outline-offset-2"
              >
                <span className="block font-medium">Se connecter en {ROLE_LABELS[account.role]}</span>
                <span className="block text-xs text-ink-400">{account.label}</span>
              </button>
            ))}
          </div>
        </div>
      ) : accountsError ? (
        <Notice tone="warn">
          <p>Les comptes de démonstration n&apos;ont pas pu être chargés.</p>
          <button
            type="button"
            onClick={() => {
              setAccountsError(false);
              setRetry((value) => value + 1);
            }}
            className="mt-1 font-medium underline hover:no-underline"
          >
            Réessayer
          </button>
        </Notice>
      ) : null}

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4" noValidate>
        <div className="[&_label]:text-ink-200 [&_p]:text-ink-400">
          <Field label="E-mail" required>
            {(inputProps) => (
              <input
                {...inputProps}
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputClassName(undefined, "dark")}
                placeholder="prenom.nom@apex-studio.demo"
              />
            )}
          </Field>
        </div>
        <div className="[&_label]:text-ink-200 [&_p]:text-ink-400">
          <Field label="Mot de passe" required>
            {(inputProps) => (
              <input
                {...inputProps}
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputClassName(undefined, "dark")}
              />
            )}
          </Field>
        </div>

        {error ? <Notice tone="danger">{error}</Notice> : null}

        <Button type="submit" loading={submitting} className="mt-2 w-full">
          Se connecter
        </Button>
      </form>
    </div>
  );
}
