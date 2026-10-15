import { Link } from "react-router-dom";
import { ArrowLeft, FileQuestion } from "lucide-react";
import { Card, EmptyState, PageHeader } from "../components/ui";

export default function NotFound() {
  return (
    <div className="animate-fade-up">
      <PageHeader eyebrow="404" title="Page not found" />
      <Card>
        <EmptyState
          icon={<FileQuestion />}
          title="That page does not exist"
          description="The link may be out of date, or the resource may have been removed."
          action={
            <Link to="/" className="dt-btn-primary">
              <ArrowLeft className="h-4 w-4" />
              Return to the dashboard
            </Link>
          }
        />
      </Card>
    </div>
  );
}
