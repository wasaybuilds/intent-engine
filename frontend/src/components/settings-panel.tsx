"use client";

import { useEffect, useState } from "react";
import { configureWebhook, getWebhookConfig } from "@/lib/api";

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  getToken: () => Promise<string | null>;
}

/**
 * Full-height right drawer for CRM webhook configuration.
 */
export function SettingsPanel({ open, onClose, getToken }: SettingsPanelProps) {
  const [webhookUrl, setWebhookUrl] = useState("");
  const [savedUrl, setSavedUrl] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!open) return;

    setIsLoading(true);
    setError("");
    getToken()
      .then((token) => getWebhookConfig(token))
      .then((config) => {
        setSavedUrl(config.webhook_url);
        setWebhookUrl(config.webhook_url ?? "");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load settings.");
      })
      .finally(() => setIsLoading(false));
  }, [open, getToken]);

  async function handleSave(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setIsSaving(true);

    try {
      const token = await getToken();
      const result = await configureWebhook(webhookUrl.trim(), token);
      setSavedUrl(result.webhook_url);
      setSuccess(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  if (!open) return null;

  return (
    <>
      <button
        type="button"
        aria-label="Close webhook panel"
        className="drawer-backdrop"
        onClick={onClose}
      />

      <aside role="dialog" aria-labelledby="settings-title" className="drawer-panel">
        <div className="drawer-header">
          <h2 id="settings-title" className="font-display text-lg font-semibold">
            Webhook
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="drawer-close"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M4 4l8 8M12 4l-8 8"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          <form onSubmit={handleSave} className="space-y-5">
            <div>
              <label
                htmlFor="webhook-url"
                className="mb-1.5 block text-sm font-medium"
                style={{ color: "var(--ink-deep)" }}
              >
                CRM webhook URL
              </label>
              <p
                className="mb-3 text-xs"
                style={{ color: "var(--ink)", opacity: 0.65 }}
              >
                Completed scrapes POST enriched leads to this URL automatically.
              </p>
              <input
                id="webhook-url"
                type="url"
                required
                disabled={isLoading || isSaving}
                placeholder="https://hooks.zapier.com/hooks/catch/..."
                value={webhookUrl}
                onChange={(event) => setWebhookUrl(event.target.value)}
                className="field-input"
              />
              {savedUrl ? (
                <p
                  className="mt-2 text-xs"
                  style={{ color: "var(--ink)", opacity: 0.7 }}
                >
                  Active: {savedUrl}
                </p>
              ) : null}
            </div>

            {error ? (
              <p role="alert" className="text-sm" style={{ color: "var(--ink)" }}>
                {error}
              </p>
            ) : null}
            {success ? (
              <p className="text-sm" style={{ color: "var(--ink)", opacity: 0.7 }}>
                {success}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={isLoading || isSaving}
              className="btn-primary w-full"
            >
              {isSaving ? "Saving…" : "Save webhook"}
            </button>
          </form>
        </div>
      </aside>
    </>
  );
}
