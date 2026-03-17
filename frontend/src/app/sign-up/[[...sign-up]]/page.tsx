import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-paper px-4">
      <div className="mb-8 text-center">
        <p className="font-display text-3xl font-semibold text-ink">
          Intent Engine
        </p>
        <p className="mt-2 text-sm text-ink/65">
          Create an account to start generating leads.
        </p>
      </div>
      <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" />
    </div>
  );
}
