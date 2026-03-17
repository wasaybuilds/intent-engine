import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-paper px-4">
      <div className="mb-8 text-center">
        <p className="font-display text-3xl font-semibold text-ink">
          Intent Engine
        </p>
        <p className="mt-2 text-sm text-ink/65">
          Sign in to run scrapes and save lead history.
        </p>
      </div>
      <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />
    </div>
  );
}
