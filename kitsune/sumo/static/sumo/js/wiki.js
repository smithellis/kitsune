import spinnerImg from "sumo/img/spinner.gif";
import "sumo/js/libs/jquery.cookie";
import "sumo/js/libs/jquery.lazyload";
import KBox from "sumo/js/kbox";
import CodeMirror from "codemirror";
import "codemirror/addon/mode/simple";
import "codemirror/addon/hint/show-hint";
import "sumo/js/libs/django/prepopulate";
import "sumo/js/codemirror.sumo-hint";
import "sumo/js/codemirror.sumo-mode";
import "sumo/js/protocol";
import AjaxPreview from "sumo/js/ajaxpreview";
import { initDiff } from "sumo/js/diff";
import Marky from "sumo/js/markup";
import ShowFor from "sumo/js/showfor";
import collapsibleAccordionInit from "sumo/js/protocol-details-init";

/*
 * wiki.js
 * Scripts for the wiki app.
 */

(function ($) {
  function init() {
    var $body = $('body');

    $('select.enable-if-js').prop("disabled", false);

    if ($body.is('.new')) {
      initPrepopulatedSlugs();
    }

    initDetailsTags();

    if ($body.is('.review')) { // Review pages
      new ShowFor();
      initNeedsChange();

      $('img.lazy').loadnow();

      // We can enable the buttons now.
      $('#actions input').prop("disabled", false);
    }

    if ($body.is('.edit_metadata, .edit, .new, .translate')) { // Document form page
      // Submit form
      $('#id_comment').on('keypress', function (e) {
        if (e.which === 13) {
          $(this).trigger('blur');
          $(this).closest('form').find('[type=submit]').trigger('click');
          return false;
        }
      });

      initExitSupportFor();
      initArticlePreview();
      initPreviewDiff();
      initTitleAndSlugCheck();
      initNeedsChange();
      initFormLock();

      $('img.lazy').loadnow();

      // We can enable the buttons now.
      $('.submit input').prop("disabled", false);
    }

    if ($body.is('.edit, .new, .translate')) {
      initPreValidation();
      initSummaryCount();
      initCodeMirrorEditor();
    }

    if ($body.is('.translate')) {  // Translate page
      initToggleDiff();
      initTranslationDraft();
    }

    initEditingTools();

    initDiffPicker();

    Marky.createFullToolbar('.editor-tools', '#id_content');

    initReadyForL10n();

    initArticleApproveModal();

    initRevisionList();

    collapsibleContributorTools();

    $('img.lazy').lazyload();
  }

  function initArticleApproveModal() {
    if ($('#approve-modal').length > 0) {
      var onSignificanceClick = function (e) {
        // Hiding if the significance is typo.
        // .parent() is because #id_is_ready_for_localization is inside a
        // <label>, as is the text
        if (e.target.id === 'id_significance_0') {
          $('#id_is_ready_for_localization').parent().hide();
        } else {
          $('#id_is_ready_for_localization').parent().show();
        }
      };

      $('#id_significance_0').on("click", onSignificanceClick);
      $('#id_significance_1').on("click", onSignificanceClick);
      $('#id_significance_2').on("click", onSignificanceClick);
    }
  }

  // Make <summary> and <details> tags work even if the browser doesn't support them.
  // From http://mathiasbynens.be/notes/html5-details-jquery
  function initDetailsTags() {
    // Note <details> tag support.
    if (!('open' in document.createElement('details'))) {
      document.documentElement.className += ' no-details';
    }

    // Execute the fallback only if there's no native `details` support
    if (!('open' in document.createElement('details'))) {
      // Loop through all `details` elements
      $('details').each(function () {
        // Store a reference to the current `details` element in a variable
        var $details = $(this),
          // Store a reference to the `summary` element of the current `details` element (if any) in a variable
          $detailsSummary = $('summary', $details),
          // Do the same for the info within the `details` element
          $detailsNotSummary = $details.children(':not(summary)'),
          // This will be used later to look for direct child text nodes
          $detailsNotSummaryContents = $details.contents(':not(summary)');

        // If there is no `summary` in the current `details` element...
        if (!$detailsSummary.length) {
          // ...create one with default text
          $detailsSummary = $(document.createElement('summary')).text('Details').prependTo($details);
        }

        // Look for direct child text nodes
        if ($detailsNotSummary.length !== $detailsNotSummaryContents.length) {
          // Wrap child text nodes in a `span` element
          $detailsNotSummaryContents.filter(function () {
            // Only keep the node in the collection if it's a text node containing more than only whitespace
            return (this.nodeType === 3) && (/[^\t\n\r ]/.test(this.data));
          }).wrap('<span>');
          // There are now no direct child text nodes anymore -- they're wrapped in `span` elements
          $detailsNotSummary = $details.children(':not(summary)');
        }

        // Hide content unless there's an `open` attribute
        if (typeof $details.attr('open') !== 'undefined') {
          $details.addClass('open');
          $detailsNotSummary.show();
        } else {
          $detailsNotSummary.hide();
        }

        // Set the `tabindex` attribute of the `summary` element to 0 to make it keyboard accessible
        $detailsSummary.attr('tabindex', 0).on("click", function () {
          // Focus on the `summary` element
          $detailsSummary.trigger('focus');
          // Toggle the `open` attribute of the `details` element
          if (typeof $details.attr('open') !== 'undefined') {
            $details.prop('open', false);
          } else {
            $details.attr('open', 'open');
          }
          // Toggle the additional information in the `details` element
          $detailsNotSummary.slideToggle();
          $details.toggleClass('open');
        }).on('keyup', function (event) {
          if (event.keyCode === 13 || event.keyCode === 32) {
            // Enter or Space is pressed -- trigger the `click` event on the `summary` element
            // Opera already seems to trigger the `click` event when Enter is pressed
            if (!($.browser.opera && event.keyCode === 13)) {
              event.preventDefault();
              $detailsSummary.trigger("click");
            }
          }
        });
      });
    }
  }

  function initPrepopulatedSlugs() {
    var fields = {
      title: {
        id: '#id_slug',
        dependency_ids: ['#id_title'],
        dependency_list: ['#id_title'],
        maxLength: 50
      }
    };

    $.each(fields, function (i, field) {
      $(field.id).addClass('prepopulated_field');
      $(field.id).data('dependency_list', field.dependency_list)
        .prepopulate($(field.dependency_ids.join(',')),
          field.maxLength);
    });
  }

  function initSummaryCount() {
    var $summaryCount = $('#remaining-characters'),
      $summaryBox = $('#id_summary'),
      // 160 characters is the maximum summary
      // length of a Google result
      warningCount = 160,
      maxCount = $summaryCount.text(),
      updateCount = function () {
        var currentCount = $summaryBox.val().length;
        $summaryCount.text(warningCount - currentCount);
        if (warningCount - currentCount >= 0) {
          $summaryCount.css('color', 'black');
        } else {
          $summaryCount.css('color', 'red');
          if (currentCount >= maxCount) {
            $summaryBox.val($summaryBox.val().substr(0, maxCount));
          }
        }
      };

    updateCount();
    $summaryBox.on('input', updateCount);
  }

  /*
   * Initialize the article preview functionality.
   */
  function initArticlePreview() {
    var $preview = $('#preview'),
      $previewBottom = $('#preview-bottom'),
      preview = new AjaxPreview($('.btn-preview'), {
        contentElement: $('#id_content'),
        previewElement: $preview
      });
    $(preview).on('done', function (e, success) {
      if (success) {
        $previewBottom.show();
        new ShowFor();
        $preview.find('select.enable-if-js').prop("disabled", false);
        $preview.find('.kbox').kbox();
        $('#preview-diff .output').empty();
        collapsibleAccordionInit();
      }
    });
  }

  // Diff Preview of edits
  function initPreviewDiff() {
    var $diff = $('#preview-diff'),
      $previewBottom = $('#preview-bottom'),
      $diffButton = $('.btn-diff');
    $diff.addClass('diff-this');
    $diffButton.on("click", function () {
      $diff.find('.to').text($('#id_content').val());
      initDiff($diff.parent());
      $previewBottom.show();
      $('#preview').empty();
    });
  }

  function initTitleAndSlugCheck() {
    $('#id_title').on('change', function () {
      var $this = $(this),
        $form = $this.closest('form'),
        title = $this.val(),
        slug = $('#id_slug').val();
      verifyTitleUnique(title, $form);
      // Check slug too, since it auto-updates and doesn't seem to fire
      // off change event.
      verifySlugUnique(slug, $form);
    });
    $('#id_slug').on('change', function () {
      var $this = $(this),
        $form = $this.closest('form'),
        slug = $('#id_slug').val();
      verifySlugUnique(slug, $form);
    });

    function verifyTitleUnique(title, $form) {
      var errorMsg = gettext('A document with this title already exists in this locale.');
      verifyUnique('title', title, $('#id_title'), $form, errorMsg);
    }

    function verifySlugUnique(slug, $form) {
      var errorMsg = gettext('A document with this slug already exists in this locale.');
      verifyUnique('slug', slug, $('#id_slug'), $form, errorMsg);
    }

    function verifyUnique(fieldname, value, $field, $form, errorMsg) {
      $field.removeClass('error');
      $field.parent().find('ul.errorlist').remove();
      var data = {};
      data[fieldname] = value;
      $.ajax({
        url: $form.data('json-url'),
        type: 'GET',
        data: data,
        dataType: 'json',
        success: function (json) {
          // Success means we found an existing doc
          var docId = $form.data('document-id');
          if (!docId || (json.id && json.id !== parseInt(docId))) {
            // Collision !!
            $field.addClass('error');
            $field.before(
              $('<ul class="errorlist"><li/></ul>')
                .find('li').text(errorMsg).end()
            );
          }
        },
        error: function (xhr, error) {
          if (xhr.status === 405) {
            // We are good!!
          } else {
            // Something went wrong, just fallback to server-side
            // validation.
          }
        }
      });
    }
  }

  // On document edit/translate/new pages, run validation before opening the
  // submit modal.
  function initPreValidation() {
    var $modal = $('#submit-modal'),
      kbox = $modal.data('kbox');
    kbox.updateOptions({
      preOpen: function () {
        var form = $('.btn-submit').closest('form')[0];
        if (form.checkValidity && !form.checkValidity()) {
          // If form isn't valid, click the modal submit button
          // so the validation error is shown. (I couldn't find a
          // better way to trigger this.)
          $modal.find('button[type="submit"]').trigger("click");
          return false;
        }
        // Add this here because the "Submit for Review" button is
        // a submit button that triggers validation and fails
        // because the modal hasn't been displayed yet.
        $modal.find('#id_comment').prop('required', true);
        return true;
      },
      preClose: function () {
        // Remove the required attribute so validation doesn't
        // fail after clicking cancel.
        $modal.find('#id_comment').prop('required', false);
        return true;
      }
    });
  }

  // The diff revision picker
  function initDiffPicker() {
    $('div.revision-diff').each(function () {
      var $diff = $(this);
      $diff.find('div.picker a').off().on("click", function (ev) {
        ev.preventDefault();
        $.ajax({
          url: $(this).attr('href'),
          type: 'GET',
          dataType: 'html',
          success: function (html) {
            var kbox = new KBox(html, {
              modal: true,
              id: 'diff-picker-kbox',
              closeOnOutClick: true,
              destroy: true,
              title: gettext('Choose revisions to compare')
            });
            kbox.open();
            ajaxifyDiffPicker(kbox.$kbox.find('form'), kbox, $diff);
          },
          error: function () {
            var message = gettext('There was an error.');
            alert(message);
          }
        });
      });
    });
  }

  function ajaxifyDiffPicker($form, kbox, $diff) {
    $form.on("submit", function (ev) {
      ev.preventDefault();
      $.ajax({
        url: $form.attr('action'),
        type: 'GET',
        data: $form.serialize(),
        dataType: 'html',
        success: function (html) {
          var $container = $diff.parent();
          kbox.close();
          $diff.replaceWith(html);
          initDiffPicker();
          initDiff();
        }
      });
    });
  }

  function initReadyForL10n() {
    var $watchDiv = $('#revision-list .l10n'),
      post_url, checkbox_id;

    $watchDiv.find('a.markasready').on("click", function () {
      var $check = $(this);
      post_url = $check.data('url');
      checkbox_id = $check.attr('id');
      $('#ready-for-l10n-modal span.revtime').html('(' + $check.data('revdate') + ')');
    });

    $('#ready-for-l10n-modal input[type=submit], #ready-for-l10n-modal button[type=submit]').on("click", function () {
      var csrf = $('#ready-for-l10n-modal input[name=csrfmiddlewaretoken]').val();
      if (post_url !== undefined && checkbox_id !== undefined) {
        $.ajax({
          type: 'POST',
          url: post_url,
          data: { csrfmiddlewaretoken: csrf },
          success: function (response) {
            $('#' + checkbox_id).removeClass('markasready').addClass('yes');
            $('#' + checkbox_id).off('click');
            Mzp.Modal.closeModal()
          },
          error: function () {
            Mzp.Modal.closeModal()
          }
        });
      }
    });
  }

  function initNeedsChange() {
    // Hide and show the comment box based on the status of the
    // "Needs change" checkbox. Also, make the textarea required
    // when checked.
    var $checkbox = $('#id_needs_change'),
      $comment = $('#id_needs_change_comment'),
      $commentlabel = $('label[for="id_needs_change_comment"]');

    if ($checkbox.length > 0) {
      updateComment();
      $checkbox.on('change', updateComment);
    }

    function updateComment() {
      if ($checkbox.is(':checked')) {
        $comment.slideDown();
        $commentlabel.slideDown();
        $comment.find('textarea').prop('required', true);
      } else {
        $commentlabel.hide();
        $comment.hide();
        $comment.find('textarea').prop('required', false);
      }
    }
  }

  function watchDiscussion() {
    // For a thread on the all discussions for a locale.
    $('.watch-form').on("click", function () {
      var form = $(this);
      $.post(form.attr('action'), form.serialize(), function () {
        form.find('.watchtoggle').toggleClass('on');
      }).error(function () {
        // error growl
      });
      return false;
    });
  }

  function initEditingTools() {
    // Init the show/hide links for editing tools
    $('#quick-links .edit a').on("click", function (ev) {
      ev.preventDefault();
      $('#doc-tabs').slideToggle('fast', function () {
        $('body').toggleClass('show-editing-tools');
      });

      if ($(this).is('.show')) {
        $.cookie('show-editing-tools', 1, { path: '/' });
      } else {
        $.cookie('show-editing-tools', null, { path: '/' });
      }
    });
  }

  function initCodeMirrorEditor() {
    window.codemirror = true;
    window.highlighting = {};

    var editor = $("<div id='editor'></div>");
    var editor_wrapper = $("<div id='editor_wrapper'></div>");

    var updateHighlightingEditor = function () {
      var currentEditor = window.highlighting.editor;
      if (!currentEditor) {
        return;
      }
      var content = $('#id_content').val();
      currentEditor.setValue(content);
    };
    window.highlighting.updateEditor = updateHighlightingEditor;

    var switch_link = $('<a></a>')
      .text(gettext('Toggle syntax highlighting'))
      .css({ textAlign: 'right', cursor: 'pointer', display: 'block' })
      .on("click", function () {
        if (editor_wrapper.css('display') === 'block') {
          editor_wrapper.css('display', 'none');
          $('#id_content').css('display', 'block');
        } else {
          updateHighlightingEditor();
          editor_wrapper.css('display', 'block');
          $('#id_content').css('display', 'none');
        }
      })

    var highlightingEnabled = function () {
      return editor_wrapper.css('display') === 'block';
    };
    window.highlighting.isEnabled = highlightingEnabled;

    editor_wrapper.append(editor);
    $('#id_content').after(switch_link).after(editor_wrapper).hide();

    document.addEventListener('DOMContentLoaded', function () {
      var cm_editor = CodeMirror(document.getElementById('editor'), {
        mode: { 'name': 'sumo' },
        value: $('#id_content').val(),
        lineNumbers: true,
        lineWrapping: true,
        extraKeys: { 'Ctrl-Space': 'autocomplete' }
      });
      window.highlighting.editor = cm_editor;

      $('#id_content').on('keyup', updateHighlightingEditor);
      updateHighlightingEditor();

      cm_editor.on('change', function (e) {
        if (!highlightingEnabled()) {
          return;
        }
        $('#id_content').val(cm_editor.getValue());
      });
    }, false);
  }

  function initFormLock() {
    var $doc = $('#edit-document');
    if (!$doc.length) {
      $doc = $('#localize-document');
    }
    if ($doc.is('.locked')) {
      var $inputs = $doc.find('input:enabled, textarea:enabled')
        .prop('disabled', true);
    }
    $('#unlock-button').on('click', function () {
      $inputs.prop('disabled', false);
      $doc.removeClass('locked');
      $('#locked-warning').slideUp(500);

      var doc_slug = $doc.data('slug');
      var url = window.location.toString();
      // Modify the current url, so we get the right locale.
      url = url.replace(/edit/, 'steal_lock');

      let xhr = new XMLHttpRequest();
      let csrf = document.querySelector('#steal-lock-form input[name=csrfmiddlewaretoken]').value;
      xhr.open("POST", url)
      if (csrf) {
        xhr.setRequestHeader('X-CSRFToken', csrf);
      }
      xhr.send();
    });
  }

  function initToggleDiff() {
    var $diff = $('#content-diff');
    var $contentOrDiff = $('#content-or-diff');

    if ($diff.length > 0) {
      $contentOrDiff
        .append($diff.clone())
        .append(
          $('<a/>')
            .text(gettext('Toggle Diff'))
            .on("click", function (e) {
              e.preventDefault();
              $contentOrDiff.toggleClass('content diff');
            }));
    }
  }

  function initTranslationDraft() {
    var $draftButton = $('.btn-draft'),
      url = $('.btn-draft').data('draft-url'),
      $draftMessage = $('#draft-message');

    $draftButton.on("click", function () {
      var message = gettext('<strong>Draft is saving...</strong>'),
        image = `<img src="${spinnerImg}">`,
        bothData = $('#both_form').serializeArray(),
        docData = $('#doc_form').serializeArray(),
        revData = $('#rev_form').serializeArray(),
        totalData = $.extend(bothData, docData, revData);

      $draftMessage.html(image + message).removeClass('success error').addClass('info').show()
      $.post(url, totalData)
        .done(function () {
          var time = new Date(),
            message = interpolate(gettext('<strong>Draft has been saved on:</strong> %s'), [time]);
          $draftMessage.html(message).toggleClass('info success').show();
        })
        .fail(function () {
          var message = gettext('<strong>Error saving draft</strong>');
          $draftMessage.html(message).toggleClass('info error').show();
        });
    });
  }

  function initRevisionList() {
    var $form = $('#revision-list form.filter');
    var $searchForm = $('.simple-search-form');

    if (!$form.length) {
      return;
    }

    const initialUrl = window.location.href;
    window.history.replaceState({ url: initialUrl }, '', initialUrl);

    function updateRevisionList(query, pushState = true) {
      $('.loading').show();

      if (query === undefined) {
        query = $form.serialize();
      }

      const baseUrl = $form.attr('action');
      const url = new URL(baseUrl, window.location.origin);
      const params = new URLSearchParams(query);

      // Update URL parameters while preserving search form state
      for (let [key, value] of params) {
        url.searchParams.set(key, value);
      }

      if (pushState) {
        window.history.pushState({ url: url.toString() }, '', url);
      }

      $('#revisions-fragment').css('opacity', 0);
      $.get(url.toString() + (url.search ? '&' : '?') + 'fragment=1', function (data) {
        $('.loading').hide();
        $('#revisions-fragment').html(data).css('opacity', 1);
      });
    }

    // Handle browser back/forward
    $(window).on('popstate', function (e) {
      if (e.originalEvent.state) {
        const url = new URL(e.originalEvent.state.url);
        const params = new URLSearchParams();

        // Copy only the parameters that belong to the revision list
        for (let [key, value] of url.searchParams) {
          if (!$searchForm.find(`[name="${key}"]`).length) {
            params.set(key, value);
          }
        }

        updateRevisionList(params.toString(), false);
      }
    });

    var timeout;
    $form.on('input change', 'input, select', function () {
      clearTimeout(timeout);
      timeout = setTimeout(function () {
        updateRevisionList();
      }, 200);

      // Save filter state but exclude pagination
      const currentData = $form.serializeArray()
        .reduce((obj, item) => {
          if (item.name !== 'page') {
            obj[item.name] = item.value;
          }
          return obj;
        }, {});
      sessionStorage.setItem('revision-list-filter', JSON.stringify(currentData));
    });

    // Handle pagination clicks
    $('#revisions-fragment').on('click', '.pagination a', function (e) {
      e.preventDefault();
      const paginationUrl = new URL($(this).attr('href'), window.location.origin);

      // Only take parameters that are not part of the search form
      const params = new URLSearchParams();
      for (let [key, value] of paginationUrl.searchParams) {
        if (!$searchForm.find(`[name="${key}"]`).length) {
          params.set(key, value);
        }
      }

      updateRevisionList(params.toString(), true);
    });

    // Remove submit button and prevent form submission
    $form.find('button, [type="submit"]').remove();
    $form.on('keydown', function (e) {
      if (e.which === 13) {
        e.preventDefault();
      }
    });
  }

  init();

  function makeWikiCollapsable() {
    // Hide the TOC
    $('#toc').hide();

    // Make sections collapsable
    $('#doc-content h1').each(function () {
      var $this = $(this);
      var $siblings = $(this).nextAll();

      var sectionElems = [];
      $siblings.each(function () {
        if ($(this).is('h1')) {
          return false;
        }
        sectionElems.push(this);
      });

      var $foldingSection = $('<div />');
      $foldingSection.addClass('wiki-section').addClass('collapsed');
      $this.before($foldingSection);
      $foldingSection.append($this);

      var $section = $('<section />');
      $foldingSection.append($section);

      for (var i = 0; i < sectionElems.length; i++) {
        $section.append(sectionElems[i]);
      }
    });

    // Make the header the trigger for toggling state
    $('#doc-content').on('click', 'h1', function () {
      $(this).closest('.wiki-section').toggleClass('collapsed');
    });

    // Expand section if deeplinked to it
    $(window.location.hash).closest('.wiki-section').removeClass('collapsed');
  };

  if ($('#doc-content').is('.collapsible')) {
    makeWikiCollapsable();
  }

  function initExitSupportFor() {
    $('#support-for-exit').on('click', function () {
      $('#support-for').remove();
    });
  }

  function collapsibleContributorTools() {
    const showMoreLink = document.getElementById('show-more-link');
    if (showMoreLink) {
      const collapsibleContent = document.querySelector('.collapsible-content');

      showMoreLink.addEventListener('click', (event) => {
        event.preventDefault();

        collapsibleContent.classList.toggle('expanded');
        showMoreLink.classList.toggle('expanded');
        showMoreLink.textContent = (showMoreLink.classList.contains('expanded')) ? 'Show Less' : 'Show More';
      });
    }

  }

})(jQuery);
