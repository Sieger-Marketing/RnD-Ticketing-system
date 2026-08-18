import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/primitives";
import { useAuth } from "@/store/auth";

export default function NotFound() {
  const user = useAuth((s) => s.user);
  return (
    <div className="card">
      <EmptyState
        title="That page does not exist"
        description="The link may be out of date, or the screen may not be built yet."
        action={
          <Link className="btn-primary" to={user?.home_route ?? "/"}>
            Back to my dashboard
          </Link>
        }
      />
    </div>
  );
}
