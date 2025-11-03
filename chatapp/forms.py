from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Profile # Import the Profile model


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        max_length=254,
        required=True,
        help_text="Required. Please provide a valid email address.",
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "form-control",
                "placeholder": field.label,
            })


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Username",
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Password",
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "form-control",
                "placeholder": field.label,
            })


# --- Add this new form by kk---
class ProfileUpdateForm(forms.ModelForm):
    """A form for updating user profile information."""
    class Meta:
        model = Profile
        fields = ['display_name', 'about_me', 'profile_picture']
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'form-control'}),
            'about_me': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'profile_picture': forms.FileInput(attrs={'style': 'display: none;', 'accept': 'image/*'}),
        }

# --- ADD THIS NEW FORM FOR CREATING GROUPS ---

class CreateGroupForm(forms.Form):
    name = forms.CharField(
        max_length=100, 
        label="Group Name",
        widget=forms.TextInput(attrs={'placeholder': 'Enter a name for your group'})
    )
    
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), # We'll set this in __init__
        widget=forms.CheckboxSelectMultiple,
        label="Select Members (from your contacts)"
    )

    def __init__(self, *args, **kwargs):
        # We must get the 'user' from the view to filter the queryset
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        
        # Get the user's contacts' profiles
        contact_profiles = self.user.profile.contacts.all()
        # Get the User objects from those profiles
        contact_users = User.objects.filter(profile__in=contact_profiles)
        
        # Set the queryset for the 'members' field
        self.fields['members'].queryset = contact_users