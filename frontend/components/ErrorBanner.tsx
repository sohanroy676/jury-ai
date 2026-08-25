/** Dismissible error banner with a stable role="alert" for tests/screen readers. */
export default function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string | null;
  onDismiss?: () => void;
}) {
  if (!message) return null;
  return (
    <div role="alert" className="error-banner">
      <span className="error-banner-message">{message}</span>
      {onDismiss && (
        <button
          type="button"
          className="error-banner-dismiss"
          onClick={onDismiss}
          aria-label="Dismiss error"
        >
          ×
        </button>
      )}
    </div>
  );
}
